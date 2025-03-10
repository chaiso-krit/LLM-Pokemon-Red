---@diagnostic disable: lowercase-global

-- Socket setup
statusSocket = nil

-- Debug buffer setup
function setupBuffer()
    debugBuffer = console:createBuffer("Debug")
    debugBuffer:setSize(100, 64)
    debugBuffer:clear()
    debugBuffer:print("Key press test initialized\n")
end

-- Global variables for key press tracking
local currentKeyIndex = nil
local keyPressStartFrame = 0
local keyPressFrames = 30 -- Hold keys for 30 frames (about 0.5 seconds)

-- Frame counter for key press duration
function frameCounter()
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
            currentKeyIndex = nil
            debugBuffer:print("Released key after " .. framesPassed .. " frames\n")
        end
    end
end

-- Socket management functions
function socketReceived()
    local data, err = statusSocket:receive(1024)
    
    if data then
        -- Trim whitespace
        data = data:gsub("^%s*(.-)%s*$", "%1")
        debugBuffer:print("Received: '" .. data .. "'\n")
        
        -- Convert to key index
        local keyIndex = tonumber(data)
        
        if keyIndex and keyIndex >= 0 and keyIndex <= 9 then
            local keyNames = { "A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L" }
            
            -- Clear any existing key press
            emu:clearKeys(0x3FF)
            currentKeyIndex = keyIndex
            keyPressStartFrame = emu:currentFrame()
            
            -- Press the key (will be held by frame counter)
            emu:addKey(keyIndex)
            debugBuffer:print("Pressing key: " .. keyNames[keyIndex + 1] .. "\n")
        else
            debugBuffer:print("Invalid key index: '" .. data .. "'\n")
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
    debugBuffer:print("Connecting to test server at 127.0.0.1:8888...\n")
    statusSocket = socket.tcp()
    
    if not statusSocket then
        debugBuffer:print("Failed to create socket\n")
        return
    end
    
    -- Add callbacks
    statusSocket:add("received", socketReceived)
    statusSocket:add("error", socketError)
    
    -- Connect to the server
    if statusSocket:connect("127.0.0.1", 8888) then
        debugBuffer:print("Successfully connected to test server\n")
    else
        debugBuffer:print("Failed to connect to test server\n")
        stopSocket()
    end
end

-- Add callbacks to run our functions
callbacks:add("start", setupBuffer)
callbacks:add("start", startSocket)
callbacks:add("frame", frameCounter)

-- Initialize on script load
if emu then
    setupBuffer()
    startSocket()
end