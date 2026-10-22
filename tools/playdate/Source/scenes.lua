-- Scene drawing for Font Lab. All specimens use font:drawText so the
-- actual font shapes its own kerning, wrap, leading and alignment; drawText
-- with width/height returns drawn width,height, which bounds scroll.
-- https://sdk.play.date/3.1.2/Inside%20Playdate.html#_fonts
-- Data is injected via init so this module never re-imports a chunk.
local Scenes = {}
local Data = nil
function Scenes.init(d)
	Data = d
end
local gfx = playdate.graphics

local function splitLines(text)
	local lines = {}
	local start = 1
	while true do
		local s, e = text:find("\n", start, true)
		if s == nil then
			lines[#lines + 1] = text:sub(start)
			break
		end
		lines[#lines + 1] = text:sub(start, s - 1)
		start = e + 1
	end
	return lines
end

-- Coverage gate: empty, badly encoded, and unsupported phrases never
-- reach a specimen.
local function gate(S, x, y)
	if S.phrase == "" then
		S.sys:drawText("Phrase empty; press A to edit.", x, y)
		return false
	end
	if not Data.validUTF8(S.phrase) then
		S.sys:drawText("Invalid text encoding; edit again.", x, y)
		return false
	end
	local missing = Data.missingScalars(S.phrase, S.coverage)
	if #missing > 0 then
		S.sys:drawText("Missing glyphs: " .. Data.formatMissing(missing), x, y)
		return false
	end
	return true
end

local function guideBox(S, x, y, w, h)
	gfx.setColor(S.fg)
	gfx.setDitherPattern(0.5, gfx.image.kDitherTypeBayer8x8)
	gfx.drawRect(x, y, w, h)
	gfx.setColor(S.fg)
end

local function originTick(S, x, y)
	gfx.setColor(S.fg)
	gfx.setDitherPattern(0.5, gfx.image.kDitherTypeBayer8x8)
	gfx.drawLine(x - 3, y, x + 3, y)
	gfx.drawLine(x, y - 3, x, y + 3)
	gfx.setColor(S.fg)
end

-- Column rect: requested width clamped to the available width, centered.
local function colRect(x, w, colW)
	local cw = math.min(colW, w)
	return x + math.floor((w - cw) / 2), cw
end

-- Worst-case text height: one scalar per line at full line advance.
local function fullHeight(S)
	local n = Data.utf8len(S.phrase) or 0
	return (n + 2) * (S.specFont:getHeight() + math.max(S.leading, 0) + 2)
end

function Scenes.reader(S, v)
	if not gate(S, v.specX, v.specY) then
		S.maxScroll = 0
		return
	end
	if S.showGuides then
		guideBox(S, S.colX, v.specY, S.colW, v.specH)
	end
	gfx.setClipRect(v.specX, v.specY, v.specW, v.specH)
	local _, drawnH = S.specFont:drawText(S.phrase, S.colX, v.specY - S.scrollPx, S.colW, fullHeight(S), S.leading, gfx.kWrapWord, S.alignConst)
	if S.showGuides then
		originTick(S, S.colX, v.specY - S.scrollPx)
	end
	gfx.clearClipRect()
	S.maxScroll = math.max(0, (drawnH or 0) - v.specH)
end

function Scenes.dialog(S, v)
	if not gate(S, v.specX, v.specY) then
		S.maxScroll = 0
		return
	end
	local boxH = 120
	local boxY = v.specY + v.specH - boxH - 2
	gfx.setColor(S.fg)
	gfx.fillRect(v.specX, boxY, v.specW, 2)
	gfx.fillRect(v.specX, boxY, 2, boxH)
	gfx.fillRect(v.specX + v.specW - 2, boxY, 2, boxH)
	gfx.fillRect(v.specX, boxY + boxH - 2, v.specW, 2)
	local tx, ty, tw, th = v.specX + 12, boxY + 10, v.specW - 24, boxH - 20
	local cx, cw = colRect(tx, tw, S.colW)
	gfx.setClipRect(tx, ty, tw, th)
	local _, drawnH = S.specFont:drawText(S.phrase, cx, ty - S.scrollPx, cw, fullHeight(S), S.leading, gfx.kWrapWord, S.alignConst)
	if S.showGuides then
		originTick(S, cx, ty - S.scrollPx)
	end
	gfx.clearClipRect()
	S.maxScroll = math.max(0, (drawnH or 0) - th)
end

function Scenes.title(S, v)
	if not gate(S, v.specX, v.specY) then
		return
	end
	guideBox(S, v.specX + 6, v.specY + 6, v.specW - 12, v.specH - 12)
	local y = v.specY + math.floor(v.specH / 4)
	local cx, cw = colRect(v.specX, v.specW, S.colW)
	gfx.setClipRect(v.specX, v.specY, v.specW, v.specH)
	S.specFont:drawText(S.phrase, cx, y, cw, fullHeight(S), S.leading, gfx.kWrapWord, S.alignConst)
	if S.showGuides then
		originTick(S, cx, y)
	end
	gfx.clearClipRect()
end

function Scenes.menu(S, v)
	if not gate(S, v.specX, v.specY) then
		return
	end
	local items = {}
	for _, line in ipairs(splitLines(S.phrase)) do
		if line ~= "" then
			items[#items + 1] = line
		end
	end
	if #items == 0 then
		S.sys:drawText("No menu items; press A to edit.", v.specX, v.specY)
		return
	end
	local h = S.specFont:getHeight() + 4
	local perView = math.max(1, math.floor((v.specH - 12) / h))
	if S.menuSel < 1 then
		S.menuSel = 1
	elseif S.menuSel > #items then
		S.menuSel = #items
	end
	local top = S.menuTop or 1
	if top < 1 then
		top = 1
	end
	if S.menuSel < top then
		top = S.menuSel
	elseif S.menuSel > top + perView - 1 then
		top = S.menuSel - perView + 1
	end
	S.menuTop = top
	local cx, cw = colRect(v.specX, v.specW, S.colW)
	gfx.setClipRect(v.specX, v.specY, v.specW, v.specH)
	local y = v.specY + 6
	for i = top, math.min(top + perView - 1, #items) do
		if i == S.menuSel then
			S.sys:drawText(">", cx, y)
		end
		S.specFont:drawText(items[i], cx + 12, y, cw - 12, h, S.leading, gfx.kWrapClip, S.alignConst)
		if S.showGuides then
			originTick(S, cx + 12, y)
		end
		y = y + h
	end
	gfx.clearClipRect()
end

local function kernBlock(S, c, y, h, tag, font, lines, layout)
	S.sys:drawText(tag, c.specX, y)
	if font == nil then
		S.sys:drawText("font failed to load", c.specX, y + S.sysH + 2)
		return
	end
	local top = y + S.sysH + 2
	local per = layout.kernPerHalf
	local start = (S.page - 1) * per + 1
	for row = 0, per - 1 do
		local text = lines[start + row]
		if text == nil then
			break
		end
		local gy = top + row * (font:getHeight() + 2)
		if gy + font:getHeight() > y + h then
			break
		end
		font:drawText(text, c.specX, gy)
		if S.showGuides then
			originTick(S, c.specX, gy)
		end
	end
end

function Scenes.kern(S, v, layout)
	local halfH = math.floor(v.specH / 2)
	if S.showGuides then
		guideBox(S, v.specX, v.specY, v.specW, v.specH)
	end
	gfx.setClipRect(v.specX, v.specY, v.specW, v.specH)
	if #S.kernLines == 0 then
		gfx.clearClipRect()
		S.sys:drawText("no kern samples supported by this font", v.specX, v.specY)
		return
	end
	if layout.kernPerHalf < 1 then
		gfx.clearClipRect()
		S.sys:drawText("font too large to fit kerning view", v.specX, v.specY)
		return
	end
	kernBlock(S, v, v.specY, halfH, "kern on", S.st.font, S.kernLines, layout)
	local offY = v.specY + halfH
	if S.unkerned == nil then
		S.sys:drawText("kern off", v.specX, offY)
		S.sys:drawText("kern-off comparison unavailable for this entry", v.specX, offY + S.sysH + 2)
	else
		kernBlock(S, v, offY, v.specY + v.specH - offY, "kern off", S.unkerned, S.kernLines, layout)
	end
	gfx.clearClipRect()
end

function Scenes.glyphs(S, v, layout)
	if layout.glyphCols < 1 or layout.glyphRows < 1 then
		S.sys:drawText("font too large to fit glyph grid", v.specX, v.specY)
		return
	end
	local list = S.glyphList
	local perPage = layout.glyphCols * layout.glyphRows
	local start = (S.page - 1) * perPage + 1
	for n = 0, perPage - 1 do
		local ch = list[start + n]
		if ch == nil then
			break
		end
		local col = n % layout.glyphCols
		local row = math.floor(n / layout.glyphCols)
		local gx = v.specX + col * layout.cellW + 3
		local gy = v.specY + row * layout.cellH + 3
		if S.showGuides then
			guideBox(S, v.specX + col * layout.cellW, v.specY + row * layout.cellH, layout.cellW, layout.cellH)
			originTick(S, gx, gy)
		end
		S.st.font:drawText(ch, gx, gy)
	end
end

return Scenes
