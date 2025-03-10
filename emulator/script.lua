---@diagnostic disable: lowercase-global

-- Socket setup for communication with Python controller
statusSocket     = nil
lastScreenshotTime = 0
screenshotInterval = 3  -- Capture screenshots every 3 seconds

-- Global variables for key press tracking
local currentKeyIndex = nil
local keyPressStartFrame = 0
local keyPressFrames = 30  -- Hold keys for 30 frames (about 0.5 seconds)

-- Debug buffer setup
function setupBuffer()
    debugBuffer = console:createBuffer("Debug")
    debugBuffer:setSize(100, 64)
    debugBuffer:clear()
    debugBuffer:print("Debug buffer initialized\n")
end

-- Screenshot capture function
function captureAndSendScreenshot()
    local currentTime = os.time()
    
    -- Only capture screenshots every 3 seconds
    if currentTime - lastScreenshotTime >= screenshotInterval then
        local screenshotPath = "/Users/alex/Documents/LLM-Pokemon-Red-Benchmark/data/screenshots/screenshot.png"
        emu:screenshot(screenshotPath) -- Take the screenshot
        sendMessage("screenshot", screenshotPath) -- Send path to Python controller
        debugBuffer:print("Screenshot captured and sent: " .. screenshotPath .. "\n")
        
        -- Update the last screenshot time
        lastScreenshotTime = currentTime
    end
end

-- Frame counter to manage key press duration
function handleKeyPress()
    -- If we're currently pressing a key
    if currentKeyIndex ~= nil then
        local currentFrame = emu:currentFrame()
        local framesPassed = currentFrame - keyPressStartFrame
        
        if framesPassed < keyPressFrames then
            -- Keep pressing the key
            emu:addKey(currentKeyIndex)
        else
            -- Release the key after sufficient frames
            emu:clearKeys(0x3FF)
            local keyNames = { "A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L" }
            debugBuffer:print("Released " .. keyNames[currentKeyIndex + 1] .. " after " .. framesPassed .. " frames\n")
            currentKeyIndex = nil
        end
    end
end

-- Socket management functions
function sendMessage(messageType, content)
    if statusSocket then
        statusSocket:send(messageType .. "||" .. content .. "\n")
    end
end

function socketReceived()
    local data, err = statusSocket:receive(1024)
    
    if data then
        -- Trim whitespace
        data = data:gsub("^%s*(.-)%s*$", "%1")
        debugBuffer:print("Received from AI controller: '" .. data .. "'\n")
        
        -- Convert to key index
        local keyIndex = tonumber(data)
        
        if keyIndex and keyIndex >= 0 and keyIndex <= 9 then
            local keyNames = { "A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L" }
            
            -- Clear existing key presses
            emu:clearKeys(0x3FF)
            
            -- Set up the key press to be held
            currentKeyIndex = keyIndex
            keyPressStartFrame = emu:currentFrame()
            
            -- Press the key (it will be held by frame callback)
            emu:addKey(keyIndex)
            debugBuffer:print("AI pressing: " .. keyNames[keyIndex + 1] .. " (will hold for " .. keyPressFrames .. " frames)\n")
        else
            debugBuffer:print("Invalid key data received: '" .. data .. "'\n")
        end
    elseif err ~= socket.ERRORS.AGAIN then
        debugBuffer:print("Socket error: " .. err .. "\n")
        stopSocket()
    end
end

function socketError(err)
    debugBuffer:print("Socket error: " .. err .. "\n")
    stopSocket()
end

function stopSocket()
    if not statusSocket then return end
    debugBuffer:print("Closing socket connection\n")
    statusSocket:close()
    statusSocket = nil
end

function startSocket()
    debugBuffer:print("Connecting to controller at 127.0.0.1:8888...\n")
    statusSocket = socket.tcp()
    
    if not statusSocket then
        debugBuffer:print("Failed to create socket\n")
        return
    end
    
    -- Add callbacks
    statusSocket:add("received", socketReceived)
    statusSocket:add("error", socketError)
    
    -- Connect to the controller
    if statusSocket:connect("127.0.0.1", 8888) then
        debugBuffer:print("Successfully connected to controller\n")
    else
        debugBuffer:print("Failed to connect to controller\n")
        stopSocket()
    end
end

-- Add callbacks to run our functions
callbacks:add("start", setupBuffer)
callbacks:add("start", startSocket)
callbacks:add("frame", captureAndSendScreenshot)
callbacks:add("frame", handleKeyPress)

-- Initialize on script load
if emu then
    setupBuffer()
    startSocket()
end