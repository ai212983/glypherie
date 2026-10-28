import "CoreLibs/keyboard"
local Data = import "data"
local Scenes = import "scenes"
local stagedEntries = import "fonts"
local stagedPhrases = import "phrases"
Scenes.init(Data)

-- SDK keyboard delete removes one byte, which can split a multibyte
-- character; trim the incomplete trailing sequence to a valid prefix.
playdate.keyboard.textChangedCallback = function()
	local t = playdate.keyboard.text or ""
	if not Data.validUTF8(t) then
		while #t > 0 and not Data.validUTF8(t) do
			t = t:sub(1, -2)
		end
		playdate.keyboard.text = t
	end
end

-- Font Lab phrase playground: realistic scenes plus kerning/glyph diagnostics.
-- Fonts render at native 1x through font:drawText (literal *, _; the font's
-- own kerning/wrap/leading/align). SDK 3.1.2 graphics/font/keyboard APIs:
-- https://sdk.play.date/3.1.2/Inside%20Playdate.html#_fonts
local gfx <const> = playdate.graphics
local sysFont = gfx.getSystemFont()

local scenes = { "reader", "dialog", "title", "menu", "kern", "glyphs" }
-- Overhang checks (j forms) plus tricky kerning pairs.
local kernLines = { "AV", "VA", "To", "Ta", "Wa", "Yo", "j", "jAj", "Ajj", "j j", "AV To j" }

local settings, customs = Data.loadStore()

local entries = {}
if type(stagedEntries) == "table" then
	entries = stagedEntries
elseif type(fonts) == "table" then
	entries = fonts
end

local loaded = {}
local phrases = {}
local phrasePos = 1
local sceneIndex = 1
local page = 1
local scrollPx = 0
local maxScroll = 0
local menuSel = 1
local settingsOpen = false
local settingsSel = 1
local settingsTop = 1
local helpTop = 1
local menuTop = 1
local editorScroll = 0
local editing = false
local showHelp = false
local editError = nil
local readyPrinted = false
local lastCoverageKey = ""

local settingRows = { "font", "phrase", "width", "align", "spacing", "ink", "kern", "guides" }
local rowLabels = { font = "font", phrase = "phrase", width = "width (phrase)", align = "align (phrase)", spacing = "spacing (phrase)", ink = "ink", kern = "kern (phrase)", guides = "guides" }
local colWidths = { 192, 288, 384 }
local leadings = { -1, 0, 2, 4 }
local aligns = { "left", "center", "right" }
local alignConsts = { left = gfx.kAlignLeft, center = gfx.kAlignCenter, right = gfx.kAlignRight }

local function entryAt(i)
	return entries[i]
end

local function entryLabel(i)
	local e = entryAt(i)
	if type(e) ~= "table" then
		return "none"
	end
	if type(e.label) == "string" and e.label ~= "" then
		return e.label
	end
	return tostring(e.font or "unnamed")
end

local function entryCharacters(e)
	if type(e) == "table" and type(e.characters) == "string" and #e.characters > 0 then
		return e.characters
	end
	return Data.defaultCharacters
end

-- Never substitute the system font for a specimen: failures stay visible.
local function loadEntry(i)
	if loaded[i] ~= nil then
		return loaded[i]
	end
	local state = { font = nil, unkerned = nil, fontErr = false, unkernedErr = false }
	local e = entryAt(i)
	if type(e) == "table" and type(e.font) == "string" and e.font ~= "" then
		state.font = gfx.font.new(e.font)
		state.fontErr = (state.font == nil)
		if type(e.unkerned) == "string" and e.unkerned ~= "" then
			state.unkerned = gfx.font.new(e.unkerned)
			state.unkernedErr = (state.unkerned == nil)
		end
	else
		state.fontErr = true
	end
	-- Coverage set from the entry repertoire: only listed scalars may be
	-- drawn with the custom font, so the SDK never falls back mid-specimen.
	state.coverage, state.list = Data.coverageOf(entryCharacters(e))
	state.kernLines = {}
	state.kernSkipped = 0
	for _, line in ipairs(kernLines) do
		if Data.fullySupported(line, state.coverage) then
			state.kernLines[#state.kernLines + 1] = line
		else
			state.kernSkipped = state.kernSkipped + 1
		end
	end
	loaded[i] = state
	return state
end

local function rebuildPhrases()
	phrases = Data.phraseList(customs, stagedPhrases)
	if #phrases == 0 then
		phrasePos = 1
		return
	end
	local pack = Data.packId(stagedPhrases)
	if settings.packId ~= pack then
		settings.packId = pack
		local pos = nil
		for i, item in ipairs(phrases) do
			if item.source == "staged" then
				pos = i
				break
			end
		end
		phrasePos = pos or Data.resolvePos(settings.phraseRef, phrases)
		settings.phraseRef = { source = phrases[phrasePos].source, index = phrases[phrasePos].index }
		Data.saveStore(settings, customs)
	else
		phrasePos = Data.resolvePos(settings.phraseRef, phrases)
		settings.phraseRef = { source = phrases[phrasePos].source, index = phrases[phrasePos].index }
	end
end

local function curPhrase()
	local item = phrases[phrasePos]
	if item == nil then
		return ""
	end
	return item.text
end

local function fontIndex()
	if #entries == 0 then
		return 1
	end
	if settings.fontIndex < 1 or settings.fontIndex > #entries then
		return 1
	end
	return settings.fontIndex
end

local function scene()
	return scenes[sceneIndex]
end

local function partnerFont(st)
	if st.unkerned ~= nil and not st.unkernedErr then
		return st.unkerned
	end
	return nil
end

local function sysH()
	return sysFont:getHeight()
end

local function chrome()
	local headerH = sysH() + 4
	local statusY = headerH + 2
	local specY = statusY + sysH() + 4
	local footerY = 240 - sysH() - 4
	return { specX = 8, specY = specY, specW = 400 - 16, specH = footerY - 2 - specY, footerY = footerY, statusY = statusY }
end

-- Coverage notes use the system font; unsupported scalars never reach a specimen.
local function viewNote(view, st)
	if view == "kern" and st.kernSkipped > 0 then
		return st.kernSkipped .. " kern sample(s) unavailable for this font"
	end
	return nil
end

-- Shared layout adjustment: views that show a coverage note get the same
-- reduced specimen rect everywhere layout is computed.
local function viewRect(view, st, c)
	local note = viewNote(view, st)
	if note == nil then
		return c, nil
	end
	local vc = { specX = c.specX, specY = c.specY + sysH() + 2, specW = c.specW, specH = c.specH - sysH() - 2 }
	return vc, note
end

local function maxPageFor(view, st, layout)
	if view ~= "kern" and view ~= "glyphs" then
		return 1
	end
	if st.font == nil then
		return 1
	end
	if view == "kern" then
		local per = layout.kernPerHalf
		if per < 1 then
			return 1
		end
		return math.max(1, math.ceil(#st.kernLines / per))
	end
	if layout.glyphCols < 1 or layout.glyphRows < 1 then
		return 1
	end
	return math.max(1, math.ceil(#st.list / (layout.glyphCols * layout.glyphRows)))
end

local function layoutFor(view, st, c)
	local layout = { kernPerHalf = 0, glyphCols = 0, glyphRows = 0, cellW = 0, cellH = 0 }
	if st.font == nil then
		return layout
	end
	-- SDK getTextWidth includes trailing padding; use the SDK value as-is.
	local fh = st.font:getHeight()
	if view == "kern" then
		local halfH = math.floor(c.specH / 2)
		layout.kernPerHalf = math.floor((halfH - sysH() - 6) / (fh + 2))
	elseif view == "glyphs" then
		local maxW = 1
		for _, ch in ipairs(st.list) do
			local w = st.font:getTextWidth(ch)
			if w > maxW then
				maxW = w
			end
		end
		layout.cellW = maxW + 6
		layout.cellH = fh + 6
		layout.glyphCols = math.floor(c.specW / layout.cellW)
		layout.glyphRows = math.floor(c.specH / layout.cellH)
	end
	return layout
end

local function resetPosition()
	page = 1
	scrollPx = 0
	maxScroll = 0
	menuSel = 1
	menuTop = 1
	editError = nil
end

local function clampPage()
	local c = chrome()
	local st = loadEntry(fontIndex())
	local vc = viewRect(scene(), st, c)
	local maxPage = maxPageFor(scene(), st, layoutFor(scene(), st, vc))
	if page < 1 then
		page = maxPage
	elseif page > maxPage then
		page = 1
	end
end

local function clampScroll()
	if scrollPx < 0 then
		scrollPx = 0
	elseif scrollPx > maxScroll then
		scrollPx = maxScroll
	end
end

local function scrollBy(amount)
	scrollPx = scrollPx + amount
	clampScroll()
end

local function setScene(i)
	sceneIndex = i
	if sceneIndex < 1 then
		sceneIndex = #scenes
	elseif sceneIndex > #scenes then
		sceneIndex = 1
	end
	resetPosition()
	clampPage()
	print("FONTLAB_VIEW view=" .. scene() .. " page=" .. page)
end

local function setFont(i)
	if #entries == 0 then
		return
	end
	settings.fontIndex = i
	if settings.fontIndex < 1 then
		settings.fontIndex = #entries
	elseif settings.fontIndex > #entries then
		settings.fontIndex = 1
	end
	resetPosition()
	clampPage()
	Data.saveStore(settings, customs)
	print("FONTLAB_FONT index=" .. settings.fontIndex .. " label=" .. entryLabel(settings.fontIndex))
end

local function setPhrasePos(pos)
	if #phrases == 0 then
		return
	end
	phrasePos = pos
	if phrasePos < 1 then
		phrasePos = #phrases
	elseif phrasePos > #phrases then
		phrasePos = 1
	end
	settings.phraseRef = { source = phrases[phrasePos].source, index = phrases[phrasePos].index }
	resetPosition()
	clampPage()
	Data.saveStore(settings, customs)
	print("FONTLAB_PHRASE ref=" .. phrases[phrasePos].source .. ":" .. phrases[phrasePos].index .. " chars=" .. Data.utf8len(phrases[phrasePos].text))
end

local function rowValue(row)
	if row == "font" then
		if #entries == 0 then
			return "none"
		end
		return entryLabel(fontIndex())
	elseif row == "phrase" then
		if #phrases == 0 then
			return "none"
		end
		return phrasePos .. "/" .. #phrases .. " " .. (Data.utf8len(curPhrase()) or 0) .. "ch"
	elseif row == "width" then
		return tostring(settings.colW) .. "px"
	elseif row == "align" then
		return settings.align
	elseif row == "spacing" then
		return string.format("%+d", settings.leading)
	elseif row == "ink" then
		return settings.ink
	elseif row == "kern" then
		local st = loadEntry(fontIndex())
		if partnerFont(st) == nil then
			return settings.kern and "on (n/a)" or "off (n/a)"
		end
		return settings.kern and "on" or "off"
	elseif row == "guides" then
		return settings.guides and "on" or "off"
	end
	return "?"
end

local function adjustRow(row, dir)
	if row == "font" then
		setFont(fontIndex() + dir)
	elseif row == "phrase" then
		setPhrasePos(phrasePos + dir)
	elseif row == "width" then
		for i, w in ipairs(colWidths) do
			if w == settings.colW then
				settings.colW = colWidths[((i - 1 + dir) % #colWidths) + 1]
				break
			end
		end
		Data.saveStore(settings, customs)
	elseif row == "align" then
		for i, a in ipairs(aligns) do
			if a == settings.align then
				settings.align = aligns[((i - 1 + dir) % #aligns) + 1]
				break
			end
		end
		Data.saveStore(settings, customs)
	elseif row == "spacing" then
		for i, l in ipairs(leadings) do
			if l == settings.leading then
				settings.leading = leadings[((i - 1 + dir) % #leadings) + 1]
				break
			end
		end
		Data.saveStore(settings, customs)
	elseif row == "ink" then
		settings.ink = (settings.ink == "dark") and "light" or "dark"
		Data.saveStore(settings, customs)
	elseif row == "kern" then
		settings.kern = not settings.kern
		Data.saveStore(settings, customs)
	elseif row == "guides" then
		settings.guides = not settings.guides
		Data.saveStore(settings, customs)
	end
	print("FONTLAB_SETTING " .. row .. "=" .. rowValue(row))
end

local function openEditor()
	if editing or playdate.keyboard.isVisible() then
		return
	end
	editing = true
	editError = nil
	editorScroll = 0
	playdate.keyboard.keyboardWillHideCallback = function(ok)
		if ok then
			local raw = playdate.keyboard.text or ""
			if not Data.validUTF8(raw) then
				editError = "Edit rejected: invalid text; kept original."
				print("FONTLAB_EDIT_REJECTED")
			elseif (Data.utf8len(raw) or 0) > Data.MAX_PHRASE then
				editError = "Edit too long: " .. (Data.utf8len(raw) or 0) .. "/" .. Data.MAX_PHRASE .. "; kept original."
				print("FONTLAB_EDIT_REJECTED")
			else
				local text = Data.truncateScalars(raw, Data.MAX_PHRASE)
				local item = phrases[phrasePos]
				if item ~= nil and item.source == "custom" and customs[item.index] ~= nil then
					customs[item.index] = text
				elseif text ~= "" then
					customs[#customs + 1] = text
					settings.phraseRef = { source = "custom", index = #customs }
				end
				rebuildPhrases()
				resetPosition()
				editError = nil
				Data.saveStore(settings, customs)
				print("FONTLAB_EDIT_OK chars=" .. (Data.utf8len(curPhrase()) or 0) .. " ref=" .. settings.phraseRef.source .. ":" .. settings.phraseRef.index)
			end
		else
			print("FONTLAB_EDIT_CANCEL")
		end
	end
	playdate.keyboard.keyboardDidHideCallback = function()
		editing = false
	end
	playdate.keyboard.show(curPhrase())
	print("FONTLAB_EDIT_OPEN chars=" .. Data.utf8len(curPhrase()))
end

local function drawSettings(c)
	local rows = #settingRows
	local rh = sysH() + 2
	local perView = math.max(1, math.floor(c.specH / rh))
	if settingsSel < 1 then
		settingsSel = 1
	elseif settingsSel > rows then
		settingsSel = rows
	end
	if settingsSel < settingsTop then
		settingsTop = settingsSel
	elseif settingsSel > settingsTop + perView - 1 then
		settingsTop = settingsSel - perView + 1
	end
	gfx.setClipRect(c.specX, c.specY, c.specW, c.specH)
	for i = settingsTop, math.min(settingsTop + perView - 1, rows) do
		local row = settingRows[i]
		local y = c.specY + (i - settingsTop) * rh
		local label = ((i == settingsSel) and "> " or "  ") .. (rowLabels[row] or row)
		sysFont:drawText(label, c.specX + 4, y)
		local value = rowValue(row)
		local vw = sysFont:getTextWidth(value)
		sysFont:drawText(value, c.specX + c.specW - vw - 4, y)
	end
	gfx.clearClipRect()
end

local function drawHelp(c)
	local lines = {
		"Font Lab: phrase playground.",
		"A edits on the device keyboard:",
		"D-pad moves, A types, B deletes,",
		"crank scrolls rows; OK commits.",
		"Computer entry: stage phrases with",
		"--text or --text-file.",
		"B opens settings; arrows change",
		"scene, scroll, rows and values.",
		"Crank scrolls reader and dialog.",
		"Menu: Help, Edit phrase, Reset.",
		"A or B closes this help.",
	}
	local rh = sysH() + 2
	local perView = math.max(1, math.floor(c.specH / rh))
	local maxTop = math.max(1, #lines - perView + 1)
	if helpTop < 1 then
		helpTop = 1
	elseif helpTop > maxTop then
		helpTop = maxTop
	end
	gfx.setClipRect(c.specX, c.specY, c.specW, c.specH)
	for i = helpTop, math.min(helpTop + perView - 1, #lines) do
		sysFont:drawText(lines[i], c.specX + 4, c.specY + (i - helpTop) * rh)
	end
	gfx.clearClipRect()
end

local function statusText(view, layout, maxPage, kernNote)
	local parts = view
	if view == "kern" or view == "glyphs" then
		parts = parts .. " p" .. page .. "/" .. maxPage
	end
	if view ~= "kern" and view ~= "glyphs" and #phrases > 0 then
		parts = parts .. " ph" .. phrasePos .. "/" .. #phrases .. " " .. (Data.utf8len(curPhrase()) or 0) .. "ch"
	end
	if kernNote ~= nil then
		parts = parts .. " " .. kernNote
	end
	return parts
end

-- Live editor view while the device keyboard is open: shows the in-progress
-- draft (not the committed phrase) with count/limit, clipped to the width
-- left of the keyboard, scrolled to the end. Draft renders in the selected
-- font only when fully covered; otherwise in the system font with a note,
-- always labeled editing so it is never mistaken for a specimen.
local function drawEditor(vc, st)
	local kbLeft = playdate.keyboard.left()
	local w = math.max(80, kbLeft - vc.specX - 8)
	local draft = playdate.keyboard.text or ""
	local n = Data.utf8len(draft) or 0
	sysFont:drawText("Editing", vc.specX, vc.specY)
	local count = n .. "/" .. Data.MAX_PHRASE
	if n > Data.MAX_PHRASE then
		count = count .. " OVER"
	end
	local countW = sysFont:getTextWidth(count)
	sysFont:drawText(count, vc.specX + w - countW, vc.specY)
	local y = vc.specY + sysH() + 2
	if draft == "" then
		sysFont:drawText("Use D-pad + A", vc.specX, y)
		editorScroll = 0
		return
	end
	local useCustom = st.font ~= nil and Data.validUTF8(draft) and Data.fullySupported(draft, st.coverage)
	if not useCustom and Data.validUTF8(draft) and st.font ~= nil then
		local missing = Data.missingScalars(draft, st.coverage)
		if #missing > 0 then
			local note = "Not in this font: " .. Data.formatMissing(missing)
			local _, noteH = sysFont:drawText(note, vc.specX, y, w, sysH() * 4, nil, gfx.kWrapWord)
			y = y + (noteH or sysH()) + 2
		end
	end
	local f = useCustom and st.font or sysFont
	local areaH = vc.specY + vc.specH - y
	if areaH < sysH() then
		areaH = sysH()
	end
	local estH = (n + 2) * (f:getHeight() + 2)
	gfx.setClipRect(vc.specX, y, w, areaH)
	local _, drawnH = f:drawText(draft, vc.specX, y - editorScroll, w, estH, 0, gfx.kWrapWord, gfx.kAlignLeft)
	gfx.clearClipRect()
	editorScroll = math.max(0, (drawnH or 0) - areaH)
end

local function draw()
	local c = chrome()
	local view = scene()
	local bg = gfx.kColorWhite
	local fg = gfx.kColorBlack
	local drawMode = gfx.kDrawModeCopy
	if settings.ink == "light" then
		bg = gfx.kColorBlack
		fg = gfx.kColorWhite
		drawMode = gfx.kDrawModeInverted
	end
	gfx.clear(bg)
	gfx.setColor(fg)
	gfx.setImageDrawMode(drawMode)

	local title = "Font Lab: " .. entryLabel(fontIndex())
	if #entries == 0 then
		title = "Font Lab: no staged fonts"
	end
	sysFont:drawText(title, 4, 2)

	local st = loadEntry(fontIndex())
	local vc, note = viewRect(view, st, c)
	if note ~= nil then
		sysFont:drawText(note, c.specX, c.specY)
	end
	if editError ~= nil then
		sysFont:drawText(editError, c.specX, vc.specY)
		vc = { specX = vc.specX, specY = vc.specY + sysH() + 2, specW = vc.specW, specH = vc.specH - sysH() - 2 }
	end
	local layout = layoutFor(view, st, vc)
	local maxPage = maxPageFor(view, st, layout)
	if page > maxPage then
		page = maxPage
	end
	local specFont = st.font
	local kernNote = nil
	if not settings.kern and partnerFont(st) ~= nil then
		specFont = partnerFont(st)
	elseif not settings.kern then
		kernNote = "kern n/a"
	end
	local colW = math.min(settings.colW, vc.specW)
	local S = {
		sys = sysFont, sysH = sysH(), fg = fg,
		phrase = curPhrase(), coverage = st.coverage,
		specFont = specFont, st = st, glyphList = st.list,
		kernLines = st.kernLines, unkerned = partnerFont(st),
		colX = vc.specX + math.floor((vc.specW - colW) / 2), colW = colW,
		leading = settings.leading, alignConst = alignConsts[settings.align],
		scrollPx = scrollPx, maxScroll = maxScroll, page = page,
		menuSel = menuSel, menuTop = menuTop, showGuides = settings.guides,
	}
	if playdate.keyboard.isVisible() then
		drawEditor(vc, st)
	elseif showHelp then
		drawHelp(vc)
	elseif settingsOpen then
		drawSettings(vc)
	elseif #entries == 0 then
		sysFont:drawText("fonts.lua missing or empty; stage fonts first", vc.specX, vc.specY)
	elseif st.font == nil then
		sysFont:drawText("font failed to load: " .. tostring(entryAt(fontIndex()).font or "?"), vc.specX, vc.specY)
	elseif view == "reader" then
		Scenes.reader(S, vc)
	elseif view == "dialog" then
		Scenes.dialog(S, vc)
	elseif view == "title" then
		Scenes.title(S, vc)
	elseif view == "menu" then
		Scenes.menu(S, vc)
	elseif view == "kern" then
		Scenes.kern(S, vc, layout)
	else
		Scenes.glyphs(S, vc, layout)
	end
	maxScroll = S.maxScroll or 0
	menuSel = S.menuSel or 1
	menuTop = S.menuTop or 1
	clampScroll()
	local status = statusText(view, layout, maxPage, kernNote)
	local sw = sysFont:getTextWidth(status)
	sysFont:drawText(status, 400 - sw - 4, c.statusY)
	local coverageKey = view .. ":" .. fontIndex() .. ":" .. phrasePos
	if coverageKey ~= lastCoverageKey then
		lastCoverageKey = coverageKey
		local missing = Data.missingScalars(curPhrase(), st.coverage)
		if curPhrase() ~= "" and #missing > 0 and view ~= "kern" and view ~= "glyphs" then
			print("FONTLAB_COVERAGE view=" .. view .. " missing=" .. #missing .. " " .. Data.formatMissing(missing))
		end
	end

	if playdate.keyboard.isVisible() then
		sysFont:drawText("A:type B:delete D-pad:move crank:rows", 4, c.footerY)
	elseif settingsOpen then
		sysFont:drawText("B:close U/D:row L/R:change", 4, c.footerY)
	elseif showHelp then
		sysFont:drawText("A/B:close U/D:scroll", 4, c.footerY)
	elseif scene() == "kern" or scene() == "glyphs" then
		sysFont:drawText("A:edit B:setup L/R:scene U/D:page", 4, c.footerY)
	elseif scene() == "menu" then
		sysFont:drawText("A:edit B:setup L/R:scene U/D:cursor", 4, c.footerY)
	else
		sysFont:drawText("A:edit B:setup L/R:scene U/D:scroll", 4, c.footerY)
	end

	gfx.setImageDrawMode(gfx.kDrawModeCopy)
	gfx.setColor(gfx.kColorBlack)

	if not readyPrinted then
		readyPrinted = true
		print("FONTLAB_READY label=" .. entryLabel(fontIndex()) .. " view=" .. view)
	end
end

local function turnPage(step)
	page = page + step
	clampPage()
end

local function handleMainInput()
	if playdate.buttonJustPressed(playdate.kButtonA) then
		openEditor()
	elseif playdate.buttonJustPressed(playdate.kButtonB) then
		settingsOpen = true
		Data.saveStore(settings, customs)
		print("FONTLAB_SETTINGS open")
	elseif playdate.buttonJustPressed(playdate.kButtonLeft) then
		setScene(sceneIndex - 1)
	elseif playdate.buttonJustPressed(playdate.kButtonRight) then
		setScene(sceneIndex + 1)
	elseif playdate.buttonJustPressed(playdate.kButtonUp) then
		if scene() == "menu" then
			menuSel = math.max(1, menuSel - 1)
		elseif scene() == "kern" or scene() == "glyphs" then
			turnPage(-1)
		else
			scrollBy(-(loadEntry(fontIndex()).font or { getHeight = function() return 8 end }):getHeight())
		end
	elseif playdate.buttonJustPressed(playdate.kButtonDown) then
		if scene() == "menu" then
			menuSel = menuSel + 1
		elseif scene() == "kern" or scene() == "glyphs" then
			turnPage(1)
		else
			scrollBy((loadEntry(fontIndex()).font or { getHeight = function() return 8 end }):getHeight())
		end
	end
	local change = playdate.getCrankChange() or 0
	if change ~= 0 then
		if scene() == "menu" then
			menuSel = math.max(1, menuSel + (change > 0 and 1 or -1))
		elseif scene() == "reader" or scene() == "dialog" then
			scrollBy(change)
		end
	end
end

local function handleSettingsInput()
	if playdate.buttonJustPressed(playdate.kButtonA) then
		openEditor()
	elseif playdate.buttonJustPressed(playdate.kButtonB) then
		settingsOpen = false
		Data.saveStore(settings, customs)
		print("FONTLAB_SETTINGS close")
	elseif playdate.buttonJustPressed(playdate.kButtonUp) then
		settingsSel = settingsSel - 1
		if settingsSel < 1 then
			settingsSel = #settingRows
		end
	elseif playdate.buttonJustPressed(playdate.kButtonDown) then
		settingsSel = settingsSel + 1
		if settingsSel > #settingRows then
			settingsSel = 1
		end
	elseif playdate.buttonJustPressed(playdate.kButtonLeft) then
		adjustRow(settingRows[settingsSel], -1)
	elseif playdate.buttonJustPressed(playdate.kButtonRight) then
		adjustRow(settingRows[settingsSel], 1)
	end
end

function playdate.update()
	if not playdate.keyboard.isVisible() then
		if showHelp then
			if playdate.buttonJustPressed(playdate.kButtonA) or playdate.buttonJustPressed(playdate.kButtonB) then
				showHelp = false
			elseif playdate.buttonJustPressed(playdate.kButtonUp) then
				helpTop = helpTop - 1
			elseif playdate.buttonJustPressed(playdate.kButtonDown) then
				helpTop = helpTop + 1
			end
		elseif settingsOpen then
			handleSettingsInput()
		else
			handleMainInput()
		end
	end
	draw()
end

local menu = playdate.getSystemMenu()
menu:addMenuItem("Help", function()
	showHelp = true
end)
menu:addMenuItem("Edit phrase", function()
	openEditor()
end)
menu:addMenuItem("Reset", function()
	settings, customs = Data.resetStore()
	phrasePos = 1
	sceneIndex = 1
	settingsSel = 1
	settingsTop = 1
	helpTop = 1
	showHelp = false
	settingsOpen = false
	resetPosition()
	rebuildPhrases()
	print("FONTLAB_RESET")
end)

rebuildPhrases()
resetPosition()
clampPage()
