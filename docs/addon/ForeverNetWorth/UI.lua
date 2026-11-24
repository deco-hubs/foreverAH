-- Forever Net Worth: the window (/nw, or the addon button in the minimap's addon menu).
local NW = ForeverNetWorth
local W, H = 440, 600
local PAD = 16
local GOLD_R, GOLD_G, GOLD_B = 0.89, 0.69, 0.28

local frame, ui

local function text(parent, font, x, y, justify, width)
  local fs = parent:CreateFontString(nil, "OVERLAY", font or "GameFontHighlight")
  fs:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
  if width then fs:SetWidth(width) end
  fs:SetJustifyH(justify or "LEFT")
  return fs
end

local function ago(t)
  if not t then return "never" end
  local s = time() - t
  if s < 3600 then return math.max(1, math.floor(s / 60)) .. " min ago" end
  if s < 86400 * 2 then return math.floor(s / 3600) .. " h ago" end
  return math.floor(s / 86400) .. " days ago"
end

local function classColor(class)
  local c = class and RAID_CLASS_COLORS and RAID_CLASS_COLORS[class]
  if c then return c.r, c.g, c.b end
  return 1, 1, 1
end

local function goalBar(parent, y)
  local label = text(parent, "GameFontHighlightSmall", PAD, y)
  local bar = CreateFrame("StatusBar", nil, parent)
  bar:SetPoint("TOPLEFT", parent, "TOPLEFT", PAD, y - 14)
  bar:SetSize(W - 2 * PAD, 10)
  bar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
  bar:SetStatusBarColor(GOLD_R, GOLD_G, GOLD_B)
  bar:SetMinMaxValues(0, 1)
  local bg = bar:CreateTexture(nil, "BACKGROUND")
  bg:SetAllPoints()
  bg:SetColorTexture(0.1, 0.1, 0.12, 0.9)
  return label, bar
end

local function build()
  frame = CreateFrame("Frame", "ForeverNetWorthFrame", UIParent, "BasicFrameTemplateWithInset")
  frame:SetSize(W, H)
  frame:SetPoint("CENTER")
  frame:SetMovable(true)
  frame:EnableMouse(true)
  frame:RegisterForDrag("LeftButton")
  frame:SetScript("OnDragStart", frame.StartMoving)
  frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
  frame:SetClampedToScreen(true)
  frame:Hide()
  tinsert(UISpecialFrames, "ForeverNetWorthFrame")   -- Escape closes it
  local title = frame.TitleText or frame.title or text(frame, "GameFontNormal", 0, -5, "CENTER", W)
  title:SetText("Forever Net Worth")

  ui = {}
  local y = -34
  ui.total = text(frame, "GameFontNormalHuge", PAD, y)
  ui.sub = text(frame, "GameFontHighlightSmall", PAD, y - 30, "LEFT", W - 2 * PAD)
  y = y - 66
  ui.goal1, ui.bar1 = goalBar(frame, y)
  ui.goal2, ui.bar2 = goalBar(frame, y - 30)
  y = y - 68

  local hdr = text(frame, "GameFontNormal", PAD, y)
  hdr:SetText("Characters")
  local COLS = { gold = 120, bags = 195, bank = 270, total = 345 }   -- x of each 70 px right-aligned column
  for _, c in ipairs({ { "Gold", "gold" }, { "Bags", "bags" }, { "Bank", "bank" }, { "Total", "total" } }) do
    text(frame, "GameFontDisableSmall", COLS[c[2]], y - 2, "RIGHT", 70):SetText(c[1])
  end
  y = y - 18
  ui.rows = {}
  for i = 1, 7 do
    local r = {}
    r.name = text(frame, "GameFontHighlightSmall", PAD, y, "LEFT", 104)
    r.name:SetWordWrap(false)
    r.gold = text(frame, "GameFontHighlightSmall", COLS.gold, y, "RIGHT", 70)
    r.bags = text(frame, "GameFontHighlightSmall", COLS.bags, y, "RIGHT", 70)
    r.bank = text(frame, "GameFontHighlightSmall", COLS.bank, y, "RIGHT", 70)
    r.total = text(frame, "GameFontHighlightSmall", COLS.total, y, "RIGHT", 70)
    ui.rows[i] = r
    y = y - 16
  end
  ui.warband = text(frame, "GameFontHighlightSmall", PAD, y, "LEFT", W - 2 * PAD)
  y = y - 24

  local th = text(frame, "GameFontNormal", PAD, y)
  th:SetText("Biggest holdings")
  y = y - 18
  ui.top = {}
  for i = 1, 8 do
    local r = {}
    r.name = text(frame, "GameFontHighlightSmall", PAD, y, "LEFT", 270)
    r.name:SetWordWrap(false)
    r.value = text(frame, "GameFontHighlightSmall", 300, y, "RIGHT", 120)
    ui.top[i] = r
    y = y - 15
  end
  y = y - 12

  local ch = text(frame, "GameFontNormal", PAD, y)
  ch:SetText("Last 30 days")
  ui.chartLabel = text(frame, "GameFontDisableSmall", 150, y - 2, "RIGHT", W - 150 - PAD)
  y = y - 18
  ui.chart = CreateFrame("Frame", nil, frame)
  ui.chart:SetPoint("TOPLEFT", frame, "TOPLEFT", PAD, y)
  ui.chart:SetSize(W - 2 * PAD, 60)
  local cbg = ui.chart:CreateTexture(nil, "BACKGROUND")
  cbg:SetAllPoints()
  cbg:SetColorTexture(0.08, 0.09, 0.11, 0.8)
  ui.bars = {}

  ui.foot = text(frame, "GameFontDisableSmall", PAD, -(H - 30), "LEFT", W - 2 * PAD)
end

-- daily closing value for the last 30 days, from the saved history
local function dailySeries(history)
  local days, out = {}, {}
  local today = math.floor(time() / 86400)
  for _, p in ipairs(history) do
    local d = math.floor(p[1] / 86400)
    if today - d < 30 then days[d] = p[2] end   -- later points overwrite: last value of the day
  end
  local lastKnown
  for d = today - 29, today do
    if days[d] then lastKnown = days[d] end
    out[#out + 1] = lastKnown or 0
  end
  return out
end

local function drawChart(series)
  local maxV = 1
  for _, v in ipairs(series) do if v > maxV then maxV = v end end
  local n = #series
  local cw, chh = ui.chart:GetWidth(), ui.chart:GetHeight()
  local bw = cw / n
  for i, v in ipairs(series) do
    local b = ui.bars[i]
    if not b then
      b = ui.chart:CreateTexture(nil, "ARTWORK")
      ui.bars[i] = b
    end
    local h = math.max(1, (v / maxV) * (chh - 4))
    b:ClearAllPoints()
    b:SetPoint("BOTTOMLEFT", ui.chart, "BOTTOMLEFT", (i - 1) * bw + 1, 2)
    b:SetSize(math.max(1, bw - 2), h)
    if i == n then b:SetColorTexture(1, 0.85, 0.45, 1) else b:SetColorTexture(GOLD_R, GOLD_G, GOLD_B, v > 0 and 0.75 or 0) end
  end
  ui.chartLabel:SetText("high " .. NW.Money(maxV, true))
end

function NW.Refresh()
  if not frame or not frame:IsShown() or not NW.db then return end
  local t = NW.Totals()
  local db = NW.db
  ui.total:SetText(NW.Money(t.total, true))
  local prices = ForeverNetWorthPrices
  local age = prices and prices.updated and ago(prices.updated) or "missing"
  local warn = (not prices or not prices.updated or time() - prices.updated > 86400 * 2) and " |cffff7f50(run the sync script)|r" or ""
  ui.sub:SetText(("Gold %s · items %s · %s after the 5%% AH cut\nAuction house prices: %s%s")
    :format(NW.Money(t.gold, true), NW.Money(t.items, true), NW.Money(t.gold + t.items * (1 - NW.AH_CUT), true), age, warn))

  for i, g in ipairs(db.goals) do
    local label, bar = ui["goal" .. i], ui["bar" .. i]
    if label then
      local frac = math.min(1, t.total / (g * NW.GOLD))
      label:SetText(("Goal %s: %d%%"):format(NW.Money(g * NW.GOLD, true), math.floor(frac * 100)))
      bar:SetValue(frac)
    end
  end

  for i, r in ipairs(ui.rows) do
    local c = t.chars[i]
    if c then
      local cr, cg, cb = classColor(c.c.class)
      local bankNote = c.c.bankSeen and NW.Money(c.bank, true) or "|cff888888open bank|r"
      r.name:SetText((c.c.name or c.key) .. (c.c.level and (" |cff888888" .. c.c.level .. "|r") or ""))
      r.name:SetTextColor(cr, cg, cb)
      r.gold:SetText(NW.Money(c.gold, true))
      r.bags:SetText(NW.Money(c.bags, true))
      r.bank:SetText(bankNote)
      r.total:SetText(NW.Money(c.total, true))
    else
      r.name:SetText(""); r.gold:SetText(""); r.bags:SetText(""); r.bank:SetText(""); r.total:SetText("")
    end
  end
  if t.warband then
    ui.warband:SetText(("Warband bank: %s  |cff888888(seen %s)|r"):format(NW.Money(t.warband, true), ago(db.warband.seen)))
  elseif #t.chars > #ui.rows then
    ui.warband:SetText(("+ %d more characters"):format(#t.chars - #ui.rows))
  else
    ui.warband:SetText("")
  end

  for i, r in ipairs(ui.top) do
    local h = t.top[i]
    if h then
      local src = h.ah and "" or " |cff888888(vendor)|r"
      r.name:SetText(("%s x %s%s"):format(BreakUpLargeNumbers and BreakUpLargeNumbers(h.count) or h.count, NW.ItemName(h.id), src))
      r.value:SetText(NW.Money(h.value, true))
    else
      r.name:SetText(""); r.value:SetText("")
    end
  end

  drawChart(dailySeries(db.history))
  ui.foot:SetText("Open your bank once on each character to include it. /nw help for commands.")
end

function NW.Toggle()
  if not frame then build() end
  if frame:IsShown() then frame:Hide() else frame:Show(); NW.Refresh() end
end
