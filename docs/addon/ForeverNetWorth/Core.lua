-- Forever Net Worth: scanning, valuation and history.
-- Read-only: it looks at your gold, bags and bank. It never buys, sells, posts or mails anything.
--
-- Saved per character (account-wide SavedVariables, so every character you log in adds itself):
--   gold   GetMoney(), whenever it changes
--   bags   rescanned when your bags change (deferred until combat ends)
--   bank   rescanned while the bank is open (the game only shows bank contents then)
-- Items are valued at the auction house market value from Prices.lua (written by the tracker,
-- copied in by the sync script). Soulbound items and items nobody sells count at vendor price.
--
-- Files share one private table (`ns`); the only globals are the saved variable, the slash
-- command and ForeverNetWorth_Toggle (needed by the TOC's AddonCompartmentFunc).

local _, ns = ...

-- ---------------------------------------------------------------- settings (change here)
ns.AH_CUT = 0.05
ns.GOLD = 10000                         -- copper per gold
local DB_VERSION = 1                    -- bump when the saved data layout changes, and add a migration below
local DEFAULT_GOALS = { 5000, 10000 }   -- gold; players change them with /nw goal 5000 10000
local HISTORY_EVERY = 30 * 60           -- one history point per 30 minutes at most
local HISTORY_MAX = 4000                -- about 80 days of points

local db, me
local bankOpen, inCombat, dirty = false, false, false

-- ---------------------------------------------------------------- containers

local GetNumSlots = C_Container.GetContainerNumSlots
local GetSlot = C_Container.GetContainerItemInfo
local GetItemInfo = C_Item.GetItemInfo

local BAGS, BANK = {}, {}
do
  for i = 0, NUM_BAG_SLOTS or 4 do BAGS[#BAGS + 1] = i end
  local E = Enum.BagIndex
  if E and E.ReagentBag then BAGS[#BAGS + 1] = E.ReagentBag end
  if E and E.CharacterBankTab_1 then
    -- tabbed bank (modern layout)
    for i = 1, 6 do
      local tab = E["CharacterBankTab_" .. i]
      if tab then BANK[#BANK + 1] = tab end
    end
  else
    -- classic layout: the bank window plus the bank bag slots after your own bags
    BANK[1] = BANK_CONTAINER or -1
    local first = (NUM_TOTAL_EQUIPPED_BAG_SLOTS or NUM_BAG_SLOTS or 4) + 1
    for i = first, first + (NUM_BANKBAGSLOTS or 7) - 1 do BANK[#BANK + 1] = i end
  end
end

-- {[itemID] = {tradeable count, soulbound count}}
local function scan(list)
  local items = {}
  for _, bag in ipairs(list) do
    for slot = 1, GetNumSlots(bag) or 0 do
      local info = GetSlot(bag, slot)
      if info and info.itemID then
        local rec = items[info.itemID]
        if not rec then rec = { 0, 0 }; items[info.itemID] = rec end
        local i = info.isBound and 2 or 1
        rec[i] = rec[i] + (info.stackCount or 1)
      end
    end
  end
  return items
end

-- ---------------------------------------------------------------- valuation

function ns.ItemName(id)
  local name = GetItemInfo(id)
  if not name then C_Item.RequestLoadItemDataByID(id); ns.waitingForInfo = true end
  return name or ("item " .. id)
end

function ns.Price(id)
  return ns.prices and ns.prices.items[id]
end

-- Auctionator (optional): its last scanned price, used for items the tracker's price file doesn't cover
-- (mostly gear). Its price is the cheapest listing at your last scan, so it's a rougher guide.
local function auctionatorPrice(id)
  local api = Auctionator and Auctionator.API and Auctionator.API.v1
  if not (api and api.GetAuctionPriceByItemID) then return nil end
  local ok, price = pcall(api.GetAuctionPriceByItemID, "ForeverNetWorth", id)
  if ok and type(price) == "number" and price > 0 then return price end
end

-- price per unit and where it came from: "ah" (tracker), "auctionator" or "vendor"
-- soulbound items can't be sold on the auction house, so they always count at vendor price
function ns.UnitValue(id, bound)
  if not bound then
    local p = ns.Price(id)
    if p then return p, "ah" end
    p = auctionatorPrice(id)
    if p then return p, "auctionator" end
  end
  local sell = select(11, GetItemInfo(id))
  if sell == nil then
    C_Item.RequestLoadItemDataByID(id)    -- not cached yet: GET_ITEM_INFO_RECEIVED recalculates
    ns.waitingForInfo = true
  end
  return sell or 0, "vendor"
end

local RANK = { ah = 3, auctionator = 2, vendor = 1 }

local function valueItems(items, holdings)
  local total = 0
  for id, rec in pairs(items or {}) do
    local v, src = 0, "vendor"
    if rec[1] > 0 then
      local p
      p, src = ns.UnitValue(id, false)
      v = rec[1] * p
    end
    if rec[2] > 0 then v = v + rec[2] * (ns.UnitValue(id, true)) end
    total = total + v
    if holdings and v > 0 then
      local h = holdings[id]
      if not h then h = { id = id, count = 0, value = 0 }; holdings[id] = h end
      h.count = h.count + rec[1] + rec[2]
      h.value = h.value + v
      if not h.src or RANK[src] > RANK[h.src] then h.src = src end
    end
  end
  return total
end

-- everything across all characters; only called for history points and when the window is open
function ns.Totals()
  local t = { chars = {}, gold = 0, items = 0 }
  local holdings = {}
  for key, c in pairs(db.chars) do
    local row = { key = key, c = c, gold = c.gold or 0,
                  bags = valueItems(c.bags, holdings), bank = valueItems(c.bank, holdings) }
    row.total = row.gold + row.bags + row.bank
    t.chars[#t.chars + 1] = row
    t.gold = t.gold + row.gold
    t.items = t.items + row.bags + row.bank
  end
  table.sort(t.chars, function(a, b) return a.total > b.total end)
  t.total = t.gold + t.items
  t.top = {}
  for _, h in pairs(holdings) do t.top[#t.top + 1] = h end
  table.sort(t.top, function(a, b) return a.value > b.value end)
  return t
end

-- ---------------------------------------------------------------- history

local function record()
  local total = math.floor(ns.Totals().total)
  local h, now = db.history, time()
  local last = h[#h]
  if last and now - last[1] < HISTORY_EVERY then
    last[2] = total                       -- same half hour: keep the latest value
  else
    h[#h + 1] = { now, total }
    if #h > HISTORY_MAX then table.remove(h, 1) end
  end
end

-- something changed: refresh the window if it's open; history is written by the ticker and at logout
local function changed()
  dirty = true
  if ns.Refresh then ns.Refresh() end
end

-- ---------------------------------------------------------------- scanning

local function scanBags()
  me.bags = scan(BAGS)
  me.gold = GetMoney()
  if bankOpen then
    me.bank = scan(BANK)
    me.bankSeen = time()
  end
  changed()
end

-- ---------------------------------------------------------------- setup and events

local function migrate()
  db.version = db.version or 1
  -- future: if db.version < 2 then ...convert... db.version = 2 end
  db.version = DB_VERSION
end

local function login()
  ForeverNetWorthDB = ForeverNetWorthDB or {}
  db = ForeverNetWorthDB
  db.chars = db.chars or {}
  db.history = db.history or {}
  db.goals = db.goals or { DEFAULT_GOALS[1], DEFAULT_GOALS[2] }
  migrate()
  local name = UnitName("player")
  local key = name .. "-" .. (GetNormalizedRealmName() or GetRealmName() or "?")
  db.chars[key] = db.chars[key] or {}
  me = db.chars[key]
  me.name, me.level = name, UnitLevel("player")
  me.class = select(2, UnitClass("player"))
  ns.db, ns.key = db, key
  scanBags()
  record()
  C_Timer.NewTicker(HISTORY_EVERY, function()
    if dirty then dirty = false; record() end
  end)
end

local f = CreateFrame("Frame")
local handlers = {}

handlers.PLAYER_LOGIN = login
handlers.PLAYER_LOGOUT = function() record() end
handlers.PLAYER_MONEY = function() me.gold = GetMoney(); changed() end
handlers.PLAYER_LEVEL_UP = function(level) me.level = level end
handlers.PLAYER_REGEN_DISABLED = function() inCombat = true end
handlers.PLAYER_REGEN_ENABLED = function()
  inCombat = false
  if ns.bagsPending then ns.bagsPending = false; scanBags() end
end
handlers.BAG_UPDATE_DELAYED = function()
  if inCombat then ns.bagsPending = true else scanBags() end
end
handlers.BANKFRAME_OPENED = function() bankOpen = true; scanBags() end
handlers.BANKFRAME_CLOSED = function() bankOpen = false end
handlers.PLAYERBANKSLOTS_CHANGED = function() if bankOpen then scanBags() end end
handlers.GET_ITEM_INFO_RECEIVED = function()
  if ns.waitingForInfo then ns.waitingForInfo = false; changed() end
end

f:SetScript("OnEvent", function(_, event, ...)
  if event ~= "PLAYER_LOGIN" and not me then return end
  handlers[event](...)
end)
for event in pairs(handlers) do
  pcall(f.RegisterEvent, f, event)        -- an event this client doesn't have is skipped, not an error
end

-- ---------------------------------------------------------------- tooltip: AH value on items

if TooltipDataProcessor and Enum.TooltipDataType then
  TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, function(tt, data)
    if tt ~= GameTooltip and tt ~= ItemRefTooltip then return end
    local p = data and data.id and ns.Price(data.id)
    if p then tt:AddDoubleLine("Forever AH market", ns.Money(p), 0.89, 0.69, 0.28, 1, 1, 1) end
  end)
end

-- ---------------------------------------------------------------- money text

local GI = "|TInterface\\MoneyFrame\\UI-GoldIcon:0:0:2:0|t"
local SI = "|TInterface\\MoneyFrame\\UI-SilverIcon:0:0:2:0|t"
local CI = "|TInterface\\MoneyFrame\\UI-CopperIcon:0:0:2:0|t"

-- short = drop silver/copper when there's gold
function ns.Money(copper, short)
  copper = math.floor((copper or 0) + 0.5)
  local sign = copper < 0 and "-" or ""
  copper = math.abs(copper)
  local g, s, c = math.floor(copper / 10000), math.floor(copper / 100) % 100, copper % 100
  if g >= 100 or (short and g > 0) then return sign .. BreakUpLargeNumbers(g) .. GI end
  if g > 0 then return sign .. g .. GI .. (s > 0 and (" " .. s .. SI) or "") end
  if s > 0 then return sign .. s .. SI .. ((c > 0 and not short) and (" " .. c .. CI) or "") end
  return sign .. c .. CI
end

-- ---------------------------------------------------------------- slash commands

local function say(msg) print("|cffe2b048Net Worth:|r " .. msg) end

SLASH_FOREVERNETWORTH1 = "/nw"
SLASH_FOREVERNETWORTH2 = "/networth"
SlashCmdList.FOREVERNETWORTH = function(msg)
  if not db then return end
  local cmd, rest = strtrim(msg or ""):match("^(%S*)%s*(.-)$")
  cmd = cmd:lower()
  if cmd == "goal" then
    local a, b = rest:match("^(%d+)%s*(%d*)$")
    if not a then return say("use /nw goal 5000 10000") end
    db.goals = { tonumber(a), tonumber(b) or db.goals[2] }
    say(("goals set to %dg and %dg."):format(db.goals[1], db.goals[2]))
    changed()
  elseif cmd == "print" then
    local t = ns.Totals()
    say(("%s  (gold %s, items %s)"):format(ns.Money(t.total, true), ns.Money(t.gold, true), ns.Money(t.items, true)))
  elseif cmd == "list" then
    for key in pairs(db.chars) do say(key) end
  elseif cmd == "forget" and rest ~= "" then
    if not db.chars[rest] then return say("no character called " .. rest .. ". /nw list shows the names.") end
    db.chars[rest] = nil
    say("forgot " .. rest .. ".")
    changed()
  elseif cmd == "resethistory" then
    db.history = {}
    record()
    say("history cleared.")
  elseif cmd == "help" then
    say("/nw  open or close the window · /nw print  totals in chat")
    say("/nw goal 5000 10000  goals in gold · /nw list · /nw forget Name-Realm · /nw resethistory")
  else
    ForeverNetWorth_Toggle()
  end
end

function ForeverNetWorth_Toggle()
  if ns.Toggle and db then ns.Toggle() end
end
