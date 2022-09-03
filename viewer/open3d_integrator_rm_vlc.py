#------------------------------------------------------------------------------
# RGBD integration using Open3D. Color information comes from one of the
# sideview grayscale cameras. Press space to stop.
#------------------------------------------------------------------------------

from pynput import keyboard

import multiprocessing as mp
import open3d as o3d
import numpy as np
import hl2ss
import hl2ss_utilities

# Settings --------------------------------------------------------------------

# HoloLens address
host = '192.168.1.15'

# Camera selection and parameters
port = hl2ss.StreamPort.RM_VLC_LEFTFRONT
model_vlc_path = '../calibration/rm_vlc_leftfront'
model_depth_path = '../calibration/rm_depth_longthrow'
profile = hl2ss.VideoProfile.H264_HIGH
bitrate = 2*1024*1024

# Buffer length in seconds
buffer_length = 10

# Integration parameters
voxel_length = 1/100
sdf_trunc = 0.04
max_depth = 3.0

#------------------------------------------------------------------------------

if __name__ == '__main__':
    enable = True

    def on_press(key):
        global enable
        enable = key != keyboard.Key.space
        return enable

    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    model_vlc = hl2ss_utilities.rm_vlc_load_pinhole_model(model_vlc_path)
    model_depth = hl2ss_utilities.rm_depth_longthrow_load_pinhole_model(model_depth_path)
    depth_scale = hl2ss_utilities.rm_depth_get_normalizer(model_depth.uv2xy)
    
    volume = o3d.pipelines.integration.ScalableTSDFVolume(voxel_length=voxel_length, sdf_trunc=sdf_trunc, color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    intrinsics_depth = o3d.camera.PinholeCameraIntrinsic(hl2ss.Parameters_RM_DEPTH_LONGTHROW.WIDTH, hl2ss.Parameters_RM_DEPTH_LONGTHROW.HEIGHT, model_depth.intrinsics[0, 0], model_depth.intrinsics[1, 1], model_depth.intrinsics[2, 0], model_depth.intrinsics[2, 1])
    vis = o3d.visualization.Visualizer()
    vis.create_window()
    first_pcd = True

    producer = hl2ss_utilities.producer()
    producer.initialize_decoded_rm_vlc(hl2ss.Parameters_RM_VLC.FPS * buffer_length, host, port, hl2ss.ChunkSize.RM_VLC, hl2ss.StreamMode.MODE_0, profile, bitrate)
    producer.initialize_decoded_rm_depth(hl2ss.Parameters_RM_DEPTH_LONGTHROW.FPS * buffer_length, host, hl2ss.StreamPort.RM_DEPTH_LONGTHROW, hl2ss.ChunkSize.RM_DEPTH_LONGTHROW, hl2ss.StreamMode.MODE_1)
    producer.start()

    manager = mp.Manager()
    consumer = hl2ss_utilities.consumer()
    sink_vlc = consumer.create_sink(producer, port, manager, None)
    sink_depth = consumer.create_sink(producer, hl2ss.StreamPort.RM_DEPTH_LONGTHROW, manager, ...)

    sinks = [sink_vlc, sink_depth]
    
    [sink.get_attach_response() for sink in sinks]

    while (enable):
        sink_depth.acquire()

        data_depth = sink_depth.get_most_recent_frame()
        if (not data_depth.is_valid_pose()):
            continue

        _, data_vlc = sink_vlc.get_nearest(data_depth.timestamp)
        if (data_vlc is None):
            continue

        depth_world_to_camera = hl2ss_utilities.rm_world_to_camera(model_depth.extrinsics, data_depth.pose)
        rgb, depth = hl2ss_utilities.rm_depth_generate_rgbd_from_rm_vlc(data_vlc.payload, data_depth.payload.depth, model_vlc.map, model_vlc.intrinsics, model_vlc.extrinsics, model_depth.map, depth_scale, model_depth.uv2xy, model_depth.extrinsics)
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(o3d.geometry.Image(np.dstack((rgb, rgb, rgb))), o3d.geometry.Image(depth), depth_scale=1, depth_trunc=max_depth, convert_rgb_to_intensity=False)

        volume.integrate(rgbd, intrinsics_depth, depth_world_to_camera.transpose())
        pcd_tmp = volume.extract_point_cloud()

        if (first_pcd):
            first_pcd = False
            pcd = pcd_tmp
            vis.add_geometry(pcd)
        else:
            pcd.points = pcd_tmp.points
            pcd.colors = pcd_tmp.colors
            vis.update_geometry(pcd)

        vis.poll_events()
        vis.update_renderer()

    [sink.detach() for sink in sinks]
    producer.stop()
    listener.join()

    vis.run()
