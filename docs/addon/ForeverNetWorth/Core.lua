-- Forever Net Worth: scanning, valuation and history.
-- Read-only: it looks at your gold, bags and bank. It never buys, sells, posts or mails anything.
--
-- What it counts, per character (saved account-wide, so every character you log in adds itself):
--   gold   GetMoney(), updated whenever it changes
--   bags   scanned whenever your bags change
--   bank   scanned while the bank is open (the game only shows bank contents then)
-- Warband / account bank (if the client has one) is counted once, not per character.
-- Items are valued at the auction house market value from Prices.lua (written by the tracker,
-- copied in by the sync script). Soulbound items and items nobody is selling count at vendor price.

local ADDON_NAME = ...
local NW = {}
_G.ForeverNetWorth = NW

NW.AH_CUT = 0.05
NW.GOLD = 10000                       -- copper per gold
local DEFAULT_GOALS = { 5000, 10000 } -- in gold, change with /nw goal 5000 10000
local HISTORY_STEP = 30 * 60          -- at most one history point per 30 minutes
local HISTORY_MAX = 4000

local db, me
local bankOpen, warbandOpen = false, false

-- ---------------------------------------------------------------- helpers

local GetNumSlots = (C_Container and C_Container.GetContainerNumSlots) or GetContainerNumSlots

local function getSlot(bag, slot)
  if C_Container and C_Container.GetContainerItemInfo then
    return C_Container.GetContainerItemInfo(bag, slot)
  end
  -- very old API fallback
  local _, count, _, _, _, _, link, _, _, id = GetContainerItemInfo(bag, slot)
  if id then return { itemID = id, stackCount = count, isBound = false } end
end

local function itemInfo(id)
  if C_Item and C_Item.GetItemInfo then return C_Item.GetItemInfo(id) end
  return GetItemInfo(id)
end

function NW.ItemName(id)
  local name = itemInfo(id)
  if not name and C_Item and C_Item.RequestLoadItemDataByID then C_Item.RequestLoadItemDataByID(id) end
  return name or ("item " .. id)
end

function NW.Money(copper, short)
  copper = math.floor((copper or 0) + 0.5)
  local neg = copper < 0
  if neg then copper = -copper end
  local g, s, c = math.floor(copper / 10000), math.floor(copper / 100) % 100, copper % 100
  local GI = "|TInterface\\MoneyFrame\\UI-GoldIcon:0:0:2:0|t"
  local SI = "|TInterface\\MoneyFrame\\UI-SilverIcon:0:0:2:0|t"
  local CI = "|TInterface\\MoneyFrame\\UI-CopperIcon:0:0:2:0|t"
  local out
  if g >= 100 or (short and g > 0) then
    out = BreakUpLargeNumbers and BreakUpLargeNumbers(g) .. GI or g .. GI
  elseif g > 0 then
    out = g .. GI .. (s > 0 and (" " .. s .. SI) or "")
  elseif s > 0 then
    out = s .. SI .. ((c > 0 and not short) and (" " .. c .. CI) or "")
  else
    out = c .. CI
  end
  return (neg and "-" or "") .. out
end

-- ---------------------------------------------------------------- containers

local function containerLists()
  local bags, bank, warband = {}, {}, {}
  local E = Enum and Enum.BagIndex
  local modern = E and E.CharacterBankTab_1 ~= nil
  if E then
    for key, idx in pairs(E) do
      local k = string.lower(key)
      if k:find("account") then
        warband[#warband + 1] = idx
      elseif k:find("bankbag") or k:find("keyring") then
        -- the bank's bag-slot container / keyring: nothing to count
      elseif k:find("bank") then
        if modern then bank[#bank + 1] = idx end
      elseif k == "backpack" or k:find("^bag_") or (modern and k:find("reagentbag")) then
        bags[#bags + 1] = idx
      end
    end
  end
  if #bags == 0 then
    for i = 0, (NUM_BAG_SLOTS or 4) do bags[#bags + 1] = i end
  end
  if not modern then
    -- classic layout: bank window (-1) plus bank bags after the bag slots
    bank = { BANK_CONTAINER or -1 }
    local first = (NUM_BAG_SLOTS or 4) + 1
    for i = first, first + (NUM_BANKBAGSLOTS or 7) - 1 do bank[#bank + 1] = i end
  end
  return bags, bank, warband
end

-- {[itemID] = {tradeable, soulbound}}
local function scan(list)
  local items = {}
  for _, bag in ipairs(list) do
    local n = GetNumSlots(bag) or 0
    for slot = 1, n do
      local info = getSlot(bag, slot)
      if info and info.itemID then
        local rec = items[info.itemID]
        if not rec then rec = { 0, 0 }; items[info.itemID] = rec end
        local count = info.stackCount or 1
        if info.isBound then rec[2] = rec[2] + count else rec[1] = rec[1] + count end
      end
    end
  end
  return items
end

-- ---------------------------------------------------------------- valuation

-- price per unit and where it came from ("ah" or "vendor")
function NW.UnitValue(id, bound)
  local prices = ForeverNetWorthPrices and ForeverNetWorthPrices.items
  local p = (not bound) and prices and prices[id]
  if p then return p, "ah" end
  local sell = select(11, itemInfo(id))
  if sell == nil and C_Item and C_Item.RequestLoadItemDataByID then
    C_Item.RequestLoadItemDataByID(id)
    NW.missingInfo = true
  end
  return sell or 0, "vendor"
end

-- total value of an item table, plus per-item values for the "top holdings" list
function NW.ValueItems(items, acc)
  local total = 0
  for id, rec in pairs(items or {}) do
    local v = 0
    if rec[1] > 0 then v = v + rec[1] * (NW.UnitValue(id, false)) end
    if rec[2] > 0 then v = v + rec[2] * (NW.UnitValue(id, true)) end
    total = total + v
    if acc and v > 0 then
      local a = acc[id]
      if not a then a = { id = id, count = 0, value = 0 }; acc[id] = a end
      a.count = a.count + rec[1] + rec[2]
      a.value = a.value + v
      a.ah = a.ah or (rec[1] > 0 and ForeverNetWorthPrices and ForeverNetWorthPrices.items[id] ~= nil)
    end
  end
  return total
end

-- everything, across all characters
function NW.Totals()
  local t = { chars = {}, holdings = {}, gold = 0, items = 0, total = 0 }
  for key, c in pairs(db.chars) do
    local bags = NW.ValueItems(c.bags, t.holdings)
    local bank = NW.ValueItems(c.bank, t.holdings)
    local row = { key = key, c = c, gold = c.gold or 0, bags = bags, bank = bank }
    row.total = row.gold + bags + bank
    t.chars[#t.chars + 1] = row
    t.gold = t.gold + row.gold
    t.items = t.items + bags + bank
  end
  table.sort(t.chars, function(a, b) return a.total > b.total end)
  if db.warband and db.warband.items then
    t.warband = NW.ValueItems(db.warband.items, t.holdings)
    t.items = t.items + t.warband
  end
  t.total = t.gold + t.items
  local list = {}
  for _, h in pairs(t.holdings) do list[#list + 1] = h end
  table.sort(list, function(a, b) return a.value > b.value end)
  t.top = list
  return t
end

-- ---------------------------------------------------------------- history

local function record()
  local t = NW.Totals()
  local now = time()
  local h = db.history
  local last = h[#h]
  if last and now - last[1] < HISTORY_STEP then
    last[2] = math.floor(t.total)        -- same half hour: update the latest point
  else
    h[#h + 1] = { now, math.floor(t.total) }
    if #h > HISTORY_MAX then table.remove(h, 1) end
  end
  NW.last = t
  if NW.Refresh then NW.Refresh() end
end

local pending = false
function NW.Update()
  if pending or not db then return end
  pending = true
  C_Timer.After(1, function()
    pending = false
    record()
  end)
end

-- ---------------------------------------------------------------- scanning

local function scanBags()
  if not me then return end
  local bags = containerLists()
  me.bags = scan(bags)
  me.gold = GetMoney()
  me.updated = time()
end

local function scanBank()
  if not me then return end
  local _, bank, warband = containerLists()
  if bankOpen then
    me.bank = scan(bank)
    me.bankSeen = time()
  end
  if (bankOpen or warbandOpen) and #warband > 0 then
    local items = scan(warband)
    if next(items) or warbandOpen then
      db.warband = { items = items, seen = time() }
    end
  end
end

-- ---------------------------------------------------------------- events

local f = CreateFrame("Frame")
local function reg(ev) pcall(f.RegisterEvent, f, ev) end  -- unknown events don't break the addon

local function isBanker(kind, accountOnly)
  local P = Enum and Enum.PlayerInteractionType
  if not P then return false end
  if accountOnly then return kind == P.AccountBanker end
  return kind == P.Banker or kind == P.CharacterBanker
end

f:SetScript("OnEvent", function(_, event, arg1)
  if event == "PLAYER_LOGIN" then
    ForeverNetWorthDB = ForeverNetWorthDB or {}
    db = ForeverNetWorthDB
    db.chars = db.chars or {}
    db.history = db.history or {}
    db.goals = db.goals or { DEFAULT_GOALS[1], DEFAULT_GOALS[2] }
    local name = UnitName("player")
    local realm = (GetNormalizedRealmName and GetNormalizedRealmName()) or GetRealmName() or "?"
    local key = name .. "-" .. realm
    db.chars[key] = db.chars[key] or {}
    me = db.chars[key]
    me.name = name
    me.class = select(2, UnitClass("player"))
    me.faction = UnitFactionGroup("player")
    me.level = UnitLevel("player")
    NW.db, NW.me, NW.key = db, me, key
    scanBags()
    NW.Update()
  elseif not me then
    return
  elseif event == "PLAYER_MONEY" then
    me.gold = GetMoney()
    NW.Update()
  elseif event == "PLAYER_LEVEL_UP" then
    me.level = arg1
  elseif event == "BAG_UPDATE_DELAYED" then
    scanBags()
    if bankOpen or warbandOpen then scanBank() end
    NW.Update()
  elseif event == "BANKFRAME_OPENED" then
    bankOpen = true
    C_Timer.After(0.5, function() scanBank(); NW.Update() end)
  elseif event == "BANKFRAME_CLOSED" then
    bankOpen, warbandOpen = false, false
  elseif event == "PLAYER_INTERACTION_MANAGER_FRAME_SHOW" then
    if isBanker(arg1) then bankOpen = true end
    if isBanker(arg1, true) then warbandOpen = true end
    if bankOpen or warbandOpen then C_Timer.After(0.5, function() scanBank(); NW.Update() end) end
  elseif event == "PLAYER_INTERACTION_MANAGER_FRAME_HIDE" then
    if isBanker(arg1) or isBanker(arg1, true) then bankOpen, warbandOpen = false, false end
  elseif event == "PLAYERBANKSLOTS_CHANGED" or event == "PLAYER_ACCOUNT_BANK_SLOTS_CHANGED" then
    if bankOpen or warbandOpen then scanBank(); NW.Update() end
  elseif event == "GET_ITEM_INFO_RECEIVED" then
    if NW.missingInfo then
      NW.missingInfo = false
      NW.Update()
    end
  end
end)

for _, ev in ipairs({ "PLAYER_LOGIN", "PLAYER_MONEY", "PLAYER_LEVEL_UP", "BAG_UPDATE_DELAYED",
  "BANKFRAME_OPENED", "BANKFRAME_CLOSED", "PLAYER_INTERACTION_MANAGER_FRAME_SHOW",
  "PLAYER_INTERACTION_MANAGER_FRAME_HIDE", "PLAYERBANKSLOTS_CHANGED",
  "PLAYER_ACCOUNT_BANK_SLOTS_CHANGED", "GET_ITEM_INFO_RECEIVED" }) do
  reg(ev)
end

-- ---------------------------------------------------------------- tooltip: AH value on items

local function addTooltipLine(tt, id)
  local p = ForeverNetWorthPrices and ForeverNetWorthPrices.items and ForeverNetWorthPrices.items[id]
  if not p then return end
  tt:AddDoubleLine("Forever AH market", NW.Money(p), 0.89, 0.69, 0.28, 1, 1, 1)
end

if TooltipDataProcessor and Enum and Enum.TooltipDataType then
  TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, function(tt, data)
    if tt ~= GameTooltip and tt ~= ItemRefTooltip then return end
    pcall(addTooltipLine, tt, data and data.id)
  end)
end

-- ---------------------------------------------------------------- slash commands

local function say(msg) print("|cffe2b048Net Worth:|r " .. msg) end

SLASH_FOREVERNETWORTH1 = "/nw"
SLASH_FOREVERNETWORTH2 = "/networth"
SlashCmdList.FOREVERNETWORTH = function(msg)
  msg = strtrim(msg or "")
  local cmd, rest = msg:match("^(%S*)%s*(.-)$")
  cmd = string.lower(cmd or "")
  if cmd == "goal" then
    local a, b = rest:match("^(%d+)%s*(%d*)$")
    if a then
      db.goals = { tonumber(a), tonumber(b) or db.goals[2] }
      say(("goals set to %dg and %dg."):format(db.goals[1], db.goals[2]))
      if NW.Refresh then NW.Refresh() end
    else
      say("use /nw goal 5000 10000")
    end
  elseif cmd == "print" then
    local t = NW.Totals()
    say(("%s  (gold %s, items %s)"):format(NW.Money(t.total, true), NW.Money(t.gold, true), NW.Money(t.items, true)))
  elseif cmd == "forget" and rest ~= "" then
    if db.chars[rest] then
      db.chars[rest] = nil
      say("forgot " .. rest .. ".")
      NW.Update()
    else
      say("no character called " .. rest .. ". Names look like Name-Realm; /nw list shows them.")
    end
  elseif cmd == "list" then
    for key in pairs(db.chars) do say(key) end
  elseif cmd == "resethistory" then
    db.history = {}
    say("history cleared.")
    NW.Update()
  elseif cmd == "help" then
    say("/nw  open or close the window")
    say("/nw print  totals in chat · /nw goal 5000 10000  set goals in gold")
    say("/nw list  your saved characters · /nw forget Name-Realm  remove one · /nw resethistory")
  else
    ForeverNetWorth_Toggle()
  end
end

function ForeverNetWorth_Toggle()
  if NW.Toggle then NW.Toggle() end
end
