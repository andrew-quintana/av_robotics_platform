"""

Author: Andrew Quintana
Email: aquintana7@gatech.edu
Version: 0.1.0
License: [License Name]

Usage:
[Usage Description]

Classes:
[Class descriptions]

Functions:
[Provide a list of functions in the module/package with a brief description of each]

Attributes:
[Provide a list of attributes in the module/package with a brief description of each]

Dependencies:
[Provide a list of external dependencies required by the module/package]

License:
[Include the full text of the license you have chosen for your code]

Examples:
[Provide some example code snippets demonstrating how to use the module/package]

"""

from utilities.utilities import *
from utilities.computational_geometry import *
from sensors.calibration.camera_calibration import calibrate_fisheye_checkerboard

import cv2
import numpy as np
import math
import apriltag

import xml.etree.ElementTree as ET

# Helper function to convert strings to numpy arrays
def string_to_numpy(string, shape, dtype=np.float32):
    return np.fromstring(string, sep=' ', dtype=dtype).reshape(shape)

class AprilTagSensor( Component ):
    
    def __init__( self, DIR ):
        super().__init__()

        inputSettingsFile = os.path.join(cal_dir, "default.xml")
        self.detector = apriltag.Detector(apriltag.DetectorOptions(families='tag16h5'))

        if not os.path.exists(inputSettingsFile):
            calibrate_fisheye_checkerboard(DIR)

        with open(inputSettingsFile, "r"):
            tree = ET.parse(inputSettingsFile)
            root = tree.getroot()

            # intrinsic parameters
            self.camera_matrix = string_to_numpy(root.find("CameraMatrix").text, (3, 3))
            self.dist_coeffs = string_to_numpy(root.find("DistCoeffs").text, (-1,))
            self.rvecs = [string_to_numpy(rvec.text, (3,)) for rvec in root.find("Rvecs")]
            self.tvecs = [string_to_numpy(tvec.text, (3,)) for tvec in root.find("Tvecs")]
            self.frame_size = tuple(map(int, root.find("FrameSize").text.split()))

        if self.logging: print("AprilTag sensor setup COMPLETE")
        
    def detect( self, image_path, measurements ):
        # Convert image to sensor filetype
        im = None
        im = cv2.imread(image_path)

        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)

        # Detect AprilTags in image
        detections = self.detector.detect(gray)

        if self.verbose: print("FOUND", len(detections), "DETECTIONS")

        for i, detection in enumerate(detections):
            
            if self.verbose: print("detection", i, ": id", detection.tag_id, "hamming", detection.hamming, "margin", detection.decision_margin)

            # Check if invalid AprilTag detected
            if detection.tag_id > 10:
                print("WARNING: INVALID APRILTAG DETECTED...")
                continue

            """# Get pose info
            info = apriltag.DetectionInfo()
            info.tagsize = 0.015
            info.fx = self.camera_matrix[0, 0]
            info.fy = self.camera_matrix[1, 1]
            info.cx = self.frame_size[0] / 2
            info.cy = self.frame_size[1] / 2
            info.det = detection"""

            # prepare camera params for detector
            fx = self.camera_matrix[0, 0]
            fy = self.camera_matrix[1, 1]
            cx = gray.shape[0] / 2
            cy = gray.shape[1] / 2
            camera_params = [fx, fy, cx, cy]

            # Get pose
            pose, tag_size, err = self.detector.detection_pose(detection, camera_params, tag_size=0.015)

            # Extract the position and orientation of the tag
            position = pose[:3,-1:]
            R = pose[:3, :3]

            if self.verbose: print("APRILTAG ID:", detection.tag_id)

            if abs(position[2,0]) > 1:
                print("WARNING: MEASUREMENT OUTSIDE OF WORKING RANGE.")
                continue

            psi_idx = 2
            
            # Convert to x, y, psi of jetbot
            x = position[2,0] * 10
            y = position[0,0] * 10 + .094
            #psi = r_state[psi_idx] * 1
            
            # Roll (φ): Rotation around the X-axis (old Y-axis)
            yaw = np.arctan2(-R[2, 1], R[2, 2])

            # Pitch (θ): Rotation around the (inverted) Y-axis
            pitch = np.arctan2(R[0, 0], -R[1, 0])

            # Yaw (ψ): Rotation around Z-axis
            yaw = np.arctan2(R[2, 0], np.sqrt(R[2, 1]**2 + R[2, 2]**2))
            
            # Yaw logarithmic offset
            a = -0.1889984804696413
            b = -0.2705714669809751
            if yaw > 0.1:
                yaw += a * np.log(x) + b
            else:
                yaw -= a * np.log(x) + b
            
            # Assign calculated and measured values
            measurements[str(detection.tag_id)] = [x, y, yaw]

            cv2.imwrite(f"{image_dir}/perspective/tag{detection.tag_id}_live.jpg", annotate(im, detection, measurements[str(detection.tag_id)]))

        return True
    
def rotation_conversion(rotation_matrix):
    
    # Create numpy array from pose.R data
    R = rotation_matrix

    # Calculate Euler angles
    roll, pitch, yaw = np.array([np.arctan2(R[2, 1], R[2, 2]),
                                            np.arctan2(-R[2, 0], np.sqrt(R[2, 1]**2 + R[2, 2]**2)),
                                            np.arctan2(R[1, 0], R[0, 0])])

    return roll, pitch, yaw

def annotate( image, detection, state ):
    # extract the bounding box (x, y)-coordinates for the AprilTag
    # and convert each of the (x, y)-coordinate pairs to integers
    (ptA, ptB, ptC, ptD) = detection.corners
    ptB = (int(ptB[0]), int(ptB[1]))
    ptC = (int(ptC[0]), int(ptC[1]))
    ptD = (int(ptD[0]), int(ptD[1]))
    ptA = (int(ptA[0]), int(ptA[1]))
    # draw the bounding box of the AprilTag detection
    cv2.line(image, ptA, ptB, (0, 255, 0), 2)
    cv2.line(image, ptB, ptC, (0, 255, 0), 2)
    cv2.line(image, ptC, ptD, (0, 255, 0), 2)
    cv2.line(image, ptD, ptA, (0, 255, 0), 2)
    # draw the center (x, y)-coordinates of the AprilTag
    (cX, cY) = (int(detection.center[0]), int(detection.center[1]))
    cv2.circle(image, (cX, cY), 5, (0, 0, 255), -1)
    # draw the tag family on the image
    tagFamily = detection.tag_family.decode("utf-8")
    tag_string = f"{tagFamily}: {detection.tag_id}"   
    pose_string = f"X: {state[0]:2f} Y: {state[1]:2f} psi: {state[2]:2f}"
    cv2.putText(image, tag_string, (ptA[0], ptA[1] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    cv2.putText(image, pose_string, (ptD[0] - 30, ptD[1] + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
    return image