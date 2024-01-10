#
# BSD 3-Clause License
#
# Copyright (c) 2019, Analog Devices, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
import aditofpython as tof
import numpy as np
import cv2 as cv
import argparse
from enum import Enum
import sys
#import keyboard

# Import OpenPose Library
try:
    sys.path.append('libs/python');
    from openpose import pyopenpose as op
except ImportError as e:
    print('Error: OpenPose library could not be found')
    raise e

# OpenPose parameters
params = {
    "model_folder": f"models/",
    "hand": True,
}

# Initialize OpenPose
opWrapper = op.WrapperPython()
opWrapper.configure(params)
opWrapper.start()

ip = "10.42.0.1" # Set to "10.42.0.1" if networking is used.
config = "config/config_adsd3500_adsd3100.json"
mode = "sr-qnative"

inWidth = 300
inHeight = 300
WHRatio = inWidth / float(inHeight)
inScaleFactor = 0.007843
meanVal = 127.5
thr = 0.2
WINDOW_NAME = "Display Objects"
WINDOW_NAME_DEPTH = "Display Objects Depth"


class ModesEnum(Enum):
    MODE_NEAR = 0
    MODE_MEDIUM = 1
    MODE_FAR = 2


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description='Script to run Skeletal Tracking Algorithm ')
    parser.add_argument("--ip", default=ip, help="IP address of ToF Device")
    parser.add_argument("--config", default=config, help="IP address of ToF Device")
    args = parser.parse_args()

    system = tof.System()

    cameras = []
    status = system.getCameraList(cameras, "ip:"+args.ip)
    if not status:
        print("system.getCameraList(): ", status)

    camera1 = cameras[0]
        
    status = camera1.setControl("initialization_config", args.config)
    print("camera1.setControl()", status)

    status = camera1.initialize()
    if not status:
        print("camera1.initialize() failed with status: ", status)

    modes = []
    status = camera1.getAvailableModes(modes)
    if not status:
        print("system.getAvailableModes() failed with status: ", status)

    status = camera1.setMode(modes[ModesEnum.MODE_NEAR.value])
    if not status:
        print("camera1.setMode() failed with status: ", status)

    types = []
    status = camera1.getAvailableFrameTypes(types)
    if not status:
        print("system.getAvailableFrameTypes() failed with status: ", status)
        
    status = camera1.setFrameType(mode)
    if not status:
        print("camera1.setFrameType() failed with status:", status)
    
    status = camera1.start()
    if not status:
        print("camera1.start() failed with status:", status)
   
    camDetails = tof.CameraDetails()
    status = camera1.getDetails(camDetails)
    if not status:
        print("system.getDetails() failed with status: ", status)

    # Enable noise reduction for better results
    smallSignalThreshold = 100
    camera1.setControl("noise_reduction_threshold", str(smallSignalThreshold))

    camera_range = 5000
    bitCount = 9
    frame = tof.Frame()

    max_value_of_IR_pixel = 2 ** bitCount - 1
    distance_scale_ir = 255.0 / max_value_of_IR_pixel
    distance_scale = 255.0 / camera_range

    while True:
    
        #if keyboard.is_pressed('q'):
        #    print("'q' key pressed. Exiting loop.")
        #    break
            
        # Capture frame-by-frame
        status = camera1.requestFrame(frame)
        if not status:
            print("camera1.requestFrame() failed with status: ", status)

        depth_map = np.array(frame.getData("depth"), dtype="uint16", copy=False)
        ir_map = np.array(frame.getData("ir"), dtype="uint16", copy=False)

        # Creation of the IR image
        ir_map = ir_map[0: int(ir_map.shape[0] / 2), :]
        ir_map = distance_scale_ir * ir_map
        ir_map = np.uint8(ir_map)
        ir_map = cv.flip(ir_map, 1)
        ir_map = cv.cvtColor(ir_map, cv.COLOR_GRAY2RGB)

        # Creation of the Depth image
        new_shape = (int(depth_map.shape[0] / 2), depth_map.shape[1])
        depth_map = np.resize(depth_map, new_shape)
        depth_map = cv.flip(depth_map, 1)
        distance_map = depth_map
        depth_map = distance_scale * depth_map
        depth_map = np.uint8(depth_map)
        depth_map = cv.applyColorMap(depth_map, cv.COLORMAP_RAINBOW)

        # Combine depth and IR for more accurate results
        result = cv.addWeighted(ir_map, 0.4, depth_map, 0.6, 0)

        cols = result.shape[1]
        rows = result.shape[0]

        if cols / float(rows) > WHRatio:
            cropSize = (int(rows * WHRatio), rows)
        else:
            cropSize = (cols, int(cols / WHRatio))

        y1 = int((rows - cropSize[1]) / 2)
        y2 = y1 + cropSize[1]
        x1 = int((cols - cropSize[0]) / 2)
        x2 = x1 + cropSize[0]
        result = result[y1:y2, x1:x2]
        depth_map = depth_map[y1:y2, x1:x2]
        distance_map = distance_map[y1:y2, x1:x2]

        cols = result.shape[1]
        rows = result.shape[0]

        # Process the frame with OpenPose
        #datum = op.Datum()
        #frame_st = np.array(depth_map)
        #datum.cvInputData = frame_st
        #opWrapper.emplaceAndPop(op.VectorDatum([datum]))

        # Display the frame
        cv.imshow("Skeletal Tracking", datum.cvOutputData)

        # Show image with object detection
        #cv.namedWindow(WINDOW_NAME, cv.WINDOW_AUTOSIZE)
        #cv.imshow(WINDOW_NAME, result)

        # Show Depth map
        #cv.namedWindow(WINDOW_NAME_DEPTH, cv.WINDOW_AUTOSIZE)
        #cv.imshow(WINDOW_NAME_DEPTH, depth_map)

        if cv.waitKey(1) >= 0:
            break
            
    camera1.stop()