-- Shared data: Unicode scalars, coverage, phrase lists, persisted store.
-- SDK contracts (3.1.2): keyboard text, datastore read/write/delete:
-- https://sdk.play.date/3.1.2/Inside%20Playdate.html
local Data = {}

Data.MAX_PHRASE = 4096
Data.STORE_FILE = "fontlab"

-- App-owned varied presets; staged phrases.lua (build worker, out only)
-- takes precedence after user customs.
Data.presets = {
	"The night bus left at eleven. Mara folded her ticket twice and watched the rain run down the window, counting the lit stops until the harbor lights came into view.",
	"MARA: You kept the map?\nJUN: Every road on it.\nMARA: Then we sleep now, and leave before dawn.",
	"Harbor Lights",
	"New Game\nContinue\nMap\nSettings\nQuit",
	"Pack my box with five dozen liquor jugs! The quick brown fox jumps over the lazy dog 0123456789.",
}

function Data.printableASCII()
	local chars = {}
	for code = 32, 126 do
		chars[#chars + 1] = string.char(code)
	end
	return table.concat(chars)
end

Data.defaultCharacters = Data.printableASCII()

function Data.validUTF8(s)
	return type(s) == "string" and utf8.len(s) ~= nil
end

-- Split a valid UTF-8 string into scalar strings; validate first.
function Data.utf8split(s)
	local list = {}
	for _, code in utf8.codes(s) do
		list[#list + 1] = utf8.char(code)
	end
	return list
end

function Data.utf8len(s)
	if not Data.validUTF8(s) then
		return nil
	end
	return utf8.len(s)
end

-- Truncate a valid UTF-8 string to max scalars.
function Data.truncateScalars(s, max)
	if utf8.len(s) <= max then
		return s
	end
	local out = {}
	local i = 0
	for _, code in utf8.codes(s) do
		i = i + 1
		if i > max then
			break
		end
		out[#out + 1] = utf8.char(code)
	end
	return table.concat(out)
end

function Data.codepoint(ch)
	local b1 = ch:byte(1)
	if b1 < 0x80 then
		return b1
	end
	local b2 = ch:byte(2) or 0x80
	if b1 < 0xE0 then
		return (b1 - 0xC0) * 64 + (b2 - 0x80)
	end
	local b3 = ch:byte(3) or 0x80
	if b1 < 0xF0 then
		return (b1 - 0xE0) * 4096 + (b2 - 0x80) * 64 + (b3 - 0x80)
	end
	local b4 = ch:byte(4) or 0x80
	return (b1 - 0xF0) * 262144 + (b2 - 0x80) * 4096 + (b3 - 0x80) * 64 + (b4 - 0x80)
end

function Data.coverageOf(charsString)
	if not Data.validUTF8(charsString) then
		charsString = Data.defaultCharacters
	end
	local set = {}
	local list = Data.utf8split(charsString)
	for _, ch in ipairs(list) do
		set[ch] = true
	end
	return set, list
end

-- Newlines are layout, not glyphs, so they never count as missing.
function Data.missingScalars(text, coverage)
	if not Data.validUTF8(text) then
		return {}
	end
	local missing = {}
	local seen = {}
	for _, ch in ipairs(Data.utf8split(text)) do
		if ch ~= "\n" and ch ~= "\r" and not coverage[ch] and not seen[ch] then
			seen[ch] = true
			missing[#missing + 1] = ch
		end
	end
	return missing
end

function Data.formatMissing(missing, maxShow)
	maxShow = maxShow or 4
	local parts = {}
	for i = 1, math.min(#missing, maxShow) do
		parts[#parts + 1] = string.format("U+%04X", Data.codepoint(missing[i]))
	end
	if #missing > maxShow then
		parts[#parts + 1] = "+" .. (#missing - maxShow) .. " more"
	end
	return table.concat(parts, " ")
end

function Data.fullySupported(text, coverage)
	return #Data.missingScalars(text, coverage) == 0
end

-- Pack identity: count, byte size, and FNV-1a over staged bytes using
-- 32-bit signed integers only (offset -2128831035; overflow wraps natively).
function Data.packId(staged)
	if type(staged) ~= "table" then
		return "none"
	end
	local n, total, hash = 0, 0, -2128831035
	for _, text in ipairs(staged) do
		if type(text) == "string" and text ~= "" then
			n = n + 1
			total = total + #text
			for i = 1, #text do
				hash = (hash ~ text:byte(i)) * 16777619
			end
		end
	end
	return n .. ":" .. total .. ":" .. hash
end

function Data.defaultSettings()
	return {
		fontIndex = 1,
		phraseRef = { source = "preset", index = 1 },
		packId = "",
		colW = 384,
		align = "left",
		leading = 0,
		ink = "dark",
		kern = true,
		guides = false,
	}
end

local function validSettings(s)
	if type(s) ~= "table" then
		return nil
	end
	local out = Data.defaultSettings()
	if type(s.fontIndex) == "number" and s.fontIndex >= 1 then
		out.fontIndex = math.floor(s.fontIndex)
	end
	if type(s.phraseRef) == "table" then
		local src = s.phraseRef.source
		if src == "custom" or src == "staged" or src == "preset" then
			out.phraseRef = { source = src, index = 1 }
			if type(s.phraseRef.index) == "number" and s.phraseRef.index >= 1 then
				out.phraseRef.index = math.floor(s.phraseRef.index)
			end
		end
	end
	if type(s.packId) == "string" then
		out.packId = s.packId
	end
	for _, w in ipairs({ 192, 288, 384 }) do
		if s.colW == w then
			out.colW = w
		end
	end
	if s.align == "left" or s.align == "center" or s.align == "right" then
		out.align = s.align
	end
	for _, l in ipairs({ -1, 0, 2, 4 }) do
		if s.leading == l then
			out.leading = l
		end
	end
	if s.ink == "light" or s.ink == "dark" then
		out.ink = s.ink
	end
	if type(s.kern) == "boolean" then
		out.kern = s.kern
	end
	if type(s.guides) == "boolean" then
		out.guides = s.guides
	end
	return out
end

local function validCustoms(list)
	local out = {}
	if type(list) ~= "table" then
		return out
	end
	for _, item in ipairs(list) do
		if type(item) == "string" and Data.validUTF8(item) and (Data.utf8len(item) or 0) <= Data.MAX_PHRASE then
			out[#out + 1] = item
		end
	end
	return out
end

function Data.loadStore()
	local settings = Data.defaultSettings()
	local customs = {}
	local ok, disk = pcall(playdate.datastore.read, Data.STORE_FILE)
	if ok and type(disk) == "table" then
		settings = validSettings(disk.settings) or settings
		customs = validCustoms(disk.customs)
	end
	return settings, customs
end

function Data.saveStore(settings, customs)
	pcall(playdate.datastore.write, { settings = settings, customs = customs }, Data.STORE_FILE)
end

function Data.resetStore()
	pcall(playdate.datastore.delete, Data.STORE_FILE)
	return Data.defaultSettings(), {}
end

-- Combined phrase list: customs first, then staged, then presets.
function Data.phraseList(customs, staged)
	local list = {}
	for i, text in ipairs(customs) do
		if Data.validUTF8(text) then
			list[#list + 1] = { source = "custom", index = i, text = text }
		end
	end
	if type(staged) == "table" then
		local n = 0
		for _, text in ipairs(staged) do
			if type(text) == "string" and text ~= "" and Data.validUTF8(text) then
				n = n + 1
				list[#list + 1] = { source = "staged", index = n, text = text }
			end
		end
	end
	for i, text in ipairs(Data.presets) do
		list[#list + 1] = { source = "preset", index = i, text = text }
	end
	return list
end

function Data.resolvePos(ref, list)
	if type(ref) == "table" then
		for pos, item in ipairs(list) do
			if item.source == ref.source and item.index == ref.index then
				return pos
			end
		end
	end
	return 1
end

return Data
