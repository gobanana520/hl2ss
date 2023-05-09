#------------------------------------------------------------------------------
# This script receives video frames and spatial input data from the HoloLens.
# The received head pointer, hand joint positions and gaze pointer are 
# projected onto the video frame.
# Press esc to stop.
#------------------------------------------------------------------------------

from pynput import keyboard

import multiprocessing as mp
import numpy as np
import cv2
import hl2ss_imshow
import hl2ss
import hl2ss_utilities
import hl2ss_mp
import hl2ss_3dcv
import hl2ss_sa

# Settings --------------------------------------------------------------------

# HoloLens 2 address
host = "192.168.1.7"

# Calibration folder (must exist but can be empty)
calibration_path = '../calibration'

# Port
port = hl2ss.StreamPort.RM_VLC_LEFTFRONT

# Video Encoding profiles
profile = hl2ss.VideoProfile.H265_MAIN

# Encoded stream average bits per second
# Must be > 0
bitrate = 1*1024*1024

# Marker properties
radius = 5
head_color  = (  0,   0, 255)
left_color  = (  0, 255,   0)
right_color = (255,   0,   0)
gaze_color  = (255,   0, 255)
thickness = -1

# Buffer length in seconds
buffer_length = 5

# Spatial Mapping settings
triangles_per_cubic_meter = 1000
mesh_threads = 2
sphere_center = [0, 0, 0]
sphere_radius = 5

#------------------------------------------------------------------------------

if __name__ == '__main__':
    # Keyboard events ---------------------------------------------------------
    enable = True

    def on_press(key):
        global enable
        enable = key != keyboard.Key.esc
        return enable

    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    # Start Spatial Mapping data manager --------------------------------------
    # Set region of 3D space to sample
    volumes = hl2ss.sm_bounding_volume()
    volumes.add_sphere(sphere_center, sphere_radius)

    # Download observed surfaces
    sm_manager = hl2ss_sa.sm_manager(host, triangles_per_cubic_meter, mesh_threads)
    sm_manager.open()
    sm_manager.set_volumes(volumes)
    sm_manager.get_observed_surfaces()

    # Get RM VLC calibration --------------------------------------------------
    # Calibration data will be downloaded if it's not in the calibration folder
    calibration_vlc = hl2ss_3dcv.get_calibration_rm(host, port, calibration_path)
    rotation_vlc = hl2ss_3dcv.rm_vlc_get_rotation(port)

    # Start RM VLC and Spatial Input streams ----------------------------------
    producer = hl2ss_mp.producer()
    producer.configure_rm_vlc(True, host, port, hl2ss.ChunkSize.RM_VLC, hl2ss.StreamMode.MODE_1, profile, bitrate)
    producer.configure_si(host, hl2ss.StreamPort.SPATIAL_INPUT, hl2ss.ChunkSize.SPATIAL_INPUT)
    producer.initialize(port, hl2ss.Parameters_RM_VLC.FPS * buffer_length)
    producer.initialize(hl2ss.StreamPort.SPATIAL_INPUT, hl2ss.Parameters_SI.SAMPLE_RATE * buffer_length)
    producer.start(port)
    producer.start(hl2ss.StreamPort.SPATIAL_INPUT)

    consumer = hl2ss_mp.consumer()
    manager = mp.Manager()
    sink_vlc = consumer.create_sink(producer, port, manager, ...)
    sink_si = consumer.create_sink(producer, hl2ss.StreamPort.SPATIAL_INPUT, manager, None)
    sink_vlc.get_attach_response()
    sink_si.get_attach_response()

    # Main Loop ---------------------------------------------------------------
    while (enable):
        # Download observed surfaces ------------------------------------------
        sm_manager.get_observed_surfaces()

        # Wait for RM VLC frame -----------------------------------------------
        sink_vlc.acquire()

        # Get RM VLC frame and nearest (in time) Spatial Input frame ----------
        _, data_vlc = sink_vlc.get_most_recent_frame()
        if ((data_vlc is None) or (not hl2ss.is_valid_pose(data_vlc.pose))):
            continue

        _, data_si = sink_si.get_nearest(data_vlc.timestamp)
        if (data_si is None):
            continue

        image = cv2.remap(data_vlc.payload, calibration_vlc.undistort_map[:, :, 0], calibration_vlc.undistort_map[:, :, 1], cv2.INTER_LINEAR)
        image = np.dstack((image, image, image))
        si = hl2ss.unpack_si(data_si.payload)

        # Compute world to RM VLC image transformation matrix -----------------
        world_to_image = hl2ss_3dcv.world_to_reference(data_vlc.pose) @ hl2ss_3dcv.rignode_to_camera(calibration_vlc.extrinsics) @ hl2ss_3dcv.camera_to_image(calibration_vlc.intrinsics)

        # Draw Head Pointer ---------------------------------------------------
        if (si.is_valid_head_pose()):
            head_pose = si.get_head_pose()
            head_ray = hl2ss_utilities.si_ray_to_vector(head_pose.position, head_pose.forward)
            d = sm_manager.cast_rays(head_ray)
            if (np.isfinite(d)):
                head_point = hl2ss_utilities.si_ray_to_point(head_ray, d)
                head_image_point = hl2ss_3dcv.project(head_point, world_to_image)
                hl2ss_utilities.draw_points(image, head_image_point.astype(np.int32), radius, head_color, thickness)

        # Draw Left Hand joints -----------------------------------------------
        if (si.is_valid_hand_left()):
            left_hand = si.get_hand_left()
            left_joints = hl2ss_utilities.si_unpack_hand(left_hand)
            left_image_points = hl2ss_3dcv.project(left_joints.positions, world_to_image)
            hl2ss_utilities.draw_points(image, left_image_points.astype(np.int32), radius, left_color, thickness)

        # Draw Right Hand joints ----------------------------------------------
        if (si.is_valid_hand_right()):
            right_hand = si.get_hand_right()
            right_joints = hl2ss_utilities.si_unpack_hand(right_hand)
            right_image_points = hl2ss_3dcv.project(right_joints.positions, world_to_image)
            hl2ss_utilities.draw_points(image, right_image_points.astype(np.int32), radius, right_color, thickness)

        # Draw Gaze Pointer ---------------------------------------------------
        if (si.is_valid_eye_ray()):
            eye_ray = si.get_eye_ray()
            eye_ray_vector = hl2ss_utilities.si_ray_to_vector(eye_ray.origin, eye_ray.direction)
            d = sm_manager.cast_rays(eye_ray_vector)
            if (np.isfinite(d)):
                gaze_point = hl2ss_utilities.si_ray_to_point(eye_ray_vector, d)
                gaze_image_point = hl2ss_3dcv.project(gaze_point, world_to_image)
                hl2ss_utilities.draw_points(image, gaze_image_point.astype(np.int32), radius, gaze_color, thickness)
                
        # Display frame -------------------------------------------------------
        cv2.imshow('Video', hl2ss_3dcv.rm_vlc_rotate_image(image, rotation_vlc))
        cv2.waitKey(1)

    # Stop Spatial Mapping data manager ---------------------------------------
    sm_manager.close()

    sink_vlc.detach()
    sink_si.detach()
    producer.stop(port)
    producer.stop(hl2ss.StreamPort.SPATIAL_INPUT)

    # Stop keyboard events ----------------------------------------------------
    listener.join()
