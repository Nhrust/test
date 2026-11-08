--   niri msg --json keyboard-layouts      → {"names": [...], "current_idx": N}
--   niri msg action switch-layout <index>

if vim.env.NIRI_SOCKET == nil or vim.fn.executable("niri") == 0 then
  return
end

local insert_layout = nil

local function get_layouts(callback)
  vim.system({ "niri", "msg", "--json", "keyboard-layouts" }, { text = true }, function(res)
    if res.code ~= 0 then return end
    local ok, data = pcall(vim.json.decode, res.stdout)
    if ok and type(data) == "table" and data.names then
      callback(data)
    end
  end)
end

local function english_index(names)
  for i, name in ipairs(names) do
    if name:find("English") then return i - 1 end
  end
  return 0
end

local function switch_to(index)
  vim.system({ "niri", "msg", "action", "switch-layout", tostring(index) })
end

local function to_english(remember)
  get_layouts(function(data)
    local en = english_index(data.names)
    if remember then insert_layout = data.current_idx end
    if data.current_idx ~= en then switch_to(en) end
  end)
end

local group = vim.api.nvim_create_augroup("LayoutSwitch", { clear = true })

vim.api.nvim_create_autocmd("InsertLeave", {
  group = group,
  callback = function() to_english(true) end,
})

vim.api.nvim_create_autocmd("InsertEnter", {
  group = group,
  callback = function()
    if insert_layout ~= nil then switch_to(insert_layout) end
  end,
})

vim.api.nvim_create_autocmd({ "VimEnter", "CmdlineEnter" }, {
  group = group,
  callback = function() to_english(false) end,
})
