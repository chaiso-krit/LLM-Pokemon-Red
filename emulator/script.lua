---@diagnostic disable: lowercase-global
-- Socket setup for communication with Python controller
statusSocket = nil
waitingForRequest = true -- New flag to indicate if we're waiting for controller request

-- Global variables for key press tracking
local currentKeyIndex = nil
local keyPressStartFrame = 0
local keyPressFrames = 2   -- Hold keys for 2 frames

-- Path to screenshot folder
local screenshotDir = ""

-- Path settings with absolute path (change this to your path)
local screenshotPath = screenshotDir .. "screenshot.png"

-- Memory addresses for Pokemon Red (Game Boy)
local memoryAddresses = {
    playerDirection = 0xC109,  -- Direction facing (0:Down, 4:Up, 8:Left, 12:Right)
    playerX = 0xD360,          -- X coordinate on map
    playerY = 0xD361,          -- Y coordinate on map
    mapId = 0xD35D,            -- Current map ID
    textmode = 0xCFC3,         -- Is textbox show
    -- Add more addresses as we discover them
}

-- Debug buffer setup
function setupBuffer()
    debugBuffer = console:createBuffer("Debug")
    debugBuffer:setSize(100, 64)
    debugBuffer:clear()
    debugBuffer:print("Debug buffer initialized\n")
end

-- Direction value to text conversion
function getDirectionText(value)
    if value == 0 then return "DOWN"
    elseif value == 4 then return "UP"
    elseif value == 8 then return "LEFT"
    elseif value == 12 then return "RIGHT"
    else return "UNKNOWN (" .. value .. ")"
    end
end

-- Read game memory data
function readGameMemory()
    local memoryData = {}
    
    -- Read direction and convert to readable form
    local directionValue = emu:read8(memoryAddresses.playerDirection)
    memoryData.direction = {
        value = directionValue,
        text = getDirectionText(directionValue)
    }
    
    -- Read coordinates
    memoryData.position = {
        x = emu:read8(memoryAddresses.playerX),
        y = emu:read8(memoryAddresses.playerY)
    }
    
    -- Read map ID
    memoryData.mapId = emu:read8(memoryAddresses.mapId)
    memoryData.textmode = emu:read8(memoryAddresses.textmode)
    
    return memoryData
end

-- Screenshot capture function with game state information
function captureAndSendScreenshot()
    -- Create directory if it doesn't exist
    os.execute("mkdir -p \"" .. screenshotDir .. "\"")
    
    -- Take the screenshot
    emu:screenshot(screenshotPath)
    
    -- Read the game memory data
    local memoryData = readGameMemory()
    
    -- Create a data package to send with the screenshot
    local dataPackage = {
        path = screenshotPath,
        direction = memoryData.direction.text,
        x = memoryData.position.x,
        y = memoryData.position.y,
        mapId = memoryData.mapId,
        textmode = memoryData.textmode
    }
    
    -- Convert to a string format for sending
    local dataString = dataPackage.path .. 
                      "||" .. dataPackage.direction .. 
                      "||" .. dataPackage.x .. 
                      "||" .. dataPackage.y .. 
                      "||" .. dataPackage.mapId ..
                      "||" .. dataPackage.textmode 
    
    -- Send combined data to Python controller
    sendMessage("screenshot_with_state", dataString)
    
    debugBuffer:print("Screenshot captured with game state:\n")
    debugBuffer:print("Direction: " .. dataPackage.direction .. "\n")
    debugBuffer:print("Position: X=" .. dataPackage.x .. ", Y=" .. dataPackage.y .. "\n")
    debugBuffer:print("Map ID: " .. dataPackage.mapId .. "\n")
    debugBuffer:print("Textbox: " .. dataPackage.textmode .. "\n")
    
    -- Set flag back to waiting for next request
    waitingForRequest = true
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
            
            -- After key press is completed, notify controller we're ready for next request
            sendMessage("ready", "true")
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
        
        -- Process different command types
        if data == "request_screenshot" then
            debugBuffer:print("Screenshot requested by controller\n")
            -- Only take screenshot if we're waiting for a request
            if waitingForRequest then
                waitingForRequest = false
                captureAndSendScreenshot()
            end
        else
            -- Assume it's a button command if not a screenshot request
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
                -- Notify we're ready for next input even if this was invalid
                waitingForRequest = true
                sendMessage("ready", "true")
            end
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
        -- Notify controller we're ready for first instruction
        sendMessage("ready", "true")
        waitingForRequest = true
    else
        debugBuffer:print("Failed to connect to controller\n")
        stopSocket()
    end
end

-- Add callbacks to run our functions
callbacks:add("start", setupBuffer)
callbacks:add("start", startSocket)
callbacks:add("frame", handleKeyPress)

-- Initialize on script load
if emu then
    setupBuffer()
    startSocket()
    
    -- Create directory on startup
    os.execute("mkdir -p \"" .. screenshotDir .. "\"")
    debugBuffer:print("Created screenshot directories\n")
end