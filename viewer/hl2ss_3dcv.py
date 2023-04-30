
import numpy as np
import os
import cv2
import open3d as o3d
import hl2ss


#------------------------------------------------------------------------------
# Transforms
#------------------------------------------------------------------------------

def get_homogeneous_component(array):
    return array[..., -1, np.newaxis]


def get_inhomogeneous_component(array):
    return array[..., 0:-1]


def to_homogeneous(array):
    return np.concatenate((array, np.ones(array.shape[0:-1] + (1,), dtype=array.dtype)), axis=-1)


def to_inhomogeneous(array):
    return get_inhomogeneous_component(array) / get_homogeneous_component(array)


def compute_uv2xy(intrinsics, width, height):
    uv2x, uv2y = np.meshgrid((np.arange(width, dtype=intrinsics.dtype)  - intrinsics[2, 0]) / intrinsics[0, 0], (np.arange(height, dtype=intrinsics.dtype) - intrinsics[2, 1]) / intrinsics[1, 1])
    return np.dstack((uv2x, uv2y))


def compute_norm(array):
    return np.linalg.norm(array, axis=-1)


def image_to_camera(intrinsics):
    return np.linalg.inv(intrinsics)


def camera_to_rignode(extrinsics):
    return np.linalg.inv(extrinsics)


def reference_to_world(pose):
    return pose


def world_to_reference(pose):
    return np.linalg.inv(pose)


def rignode_to_camera(extrinsics):
    return extrinsics


def camera_to_image(intrinsics):
    return intrinsics


def block_to_list(points):
    return points.reshape((-1, points.shape[-1]))


def list_to_block(height, width, points):
    return points.reshape((height, width, -1))


def slice_to_block(slice):
    return slice[:, :, np.newaxis]


def transform(points, transform4x4):
    return points @ transform4x4[:3, :3] + transform4x4[3, :3].reshape(([1] * (len(points.shape) - 1)).append(3))


def project(points, projection4x4):
    return to_inhomogeneous(transform(points, projection4x4))


def extrinsics_to_Rt(extrinsics):
    return (extrinsics[:3, :3], extrinsics[3, :3].reshape((1, 3)))


def vector_to_skew_symmetric(vector):
    return np.array([[0, vector[0, 2], -vector[0, 1]], [-vector[0, 2], 0, vector[0, 0]], [vector[0, 1], -vector[0, 0], 0]], dtype=vector.dtype)


def Rt_to_essential(R, t_skew):
    return R @ t_skew


def essential_to_fundamental(image_to_camera_1, image_to_camera_2, essential):
    return image_to_camera_1 @ essential @ image_to_camera_2.transpose()


#------------------------------------------------------------------------------
# RM VLC
#------------------------------------------------------------------------------

def rm_vlc_get_rotation(port):
    if (port == hl2ss.StreamPort.RM_VLC_LEFTFRONT):
        return cv2.ROTATE_90_CLOCKWISE
    if (port == hl2ss.StreamPort.RM_VLC_LEFTLEFT):
        return cv2.ROTATE_90_COUNTERCLOCKWISE
    if (port == hl2ss.StreamPort.RM_VLC_RIGHTFRONT):
        return cv2.ROTATE_90_COUNTERCLOCKWISE
    if (port == hl2ss.StreamPort.RM_VLC_RIGHTRIGHT):
        return cv2.ROTATE_90_CLOCKWISE
    
    return None


def rm_vlc_rotate_intrinsics(intrinsics, rotation):
    rw = hl2ss.Parameters_RM_VLC.WIDTH  - 1
    bh = hl2ss.Parameters_RM_VLC.HEIGHT - 1

    fx = intrinsics[0, 0]
    fy = intrinsics[1, 1]
    cx = intrinsics[2, 0]
    cy = intrinsics[2, 1]

    if (rotation == cv2.ROTATE_90_CLOCKWISE):
        return np.array([[fy, 0, 0, 0], [0, fx, 0, 0], [(bh-cy), cx, 1, 0], [0, 0, 0, 1]], dtype=intrinsics.dtype)
    if (rotation == cv2.ROTATE_90_COUNTERCLOCKWISE):
        return np.array([[fy, 0, 0, 0], [0, fx, 0, 0], [cy, (rw-cx), 1, 0], [0, 0, 0, 1]], dtype=intrinsics.dtype)

    return None


def rm_vlc_rotate_extrinsics(extrinsics, rotation):
    if (rotation == cv2.ROTATE_90_CLOCKWISE):
        return extrinsics @ np.array([[0, 1, 0, 0], [-1, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=extrinsics.dtype)
    if (rotation == cv2.ROTATE_90_COUNTERCLOCKWISE):
        return extrinsics @ np.array([[0, -1, 0, 0], [1, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=extrinsics.dtype)
    
    return None


def rm_vlc_rotate_calibration(intrinsics, extrinsics, rotation):
    return (rm_vlc_rotate_intrinsics(intrinsics, rotation), rm_vlc_rotate_extrinsics(extrinsics, rotation))


def rm_vlc_rotate_image(image, rotation):
    return cv2.rotate(image, rotation)


def rm_vlc_to_rgb(image):
    return np.dstack((image, image, image))


#------------------------------------------------------------------------------
# RM Depth
#------------------------------------------------------------------------------

def rm_depth_normalize(depth, scale):
    return slice_to_block(depth / scale)


def rm_depth_undistort(depth, undistort_map):
    return cv2.remap(depth, undistort_map[:, :, 0], undistort_map[:, :, 1], cv2.INTER_NEAREST)


def rm_depth_to_float(image):
    return image.astype(np.float32) / hl2ss._RANGEOF.U16_MAX


def rm_depth_to_uint8(image):
    return (image / (hl2ss._RANGEOF.U8_MAX + 1)).astype(np.uint8)


def rm_depth_compute_rays(uv2xy, depth_scale):
    xy1 = to_homogeneous(uv2xy)
    scale = compute_norm(xy1) * depth_scale
    return (xy1, scale)


def rm_depth_to_points(rays, depth):
    return rays * depth


def rm_depth_to_rgb(image):
    return np.dstack((image, image, image))


#------------------------------------------------------------------------------
# PV
#------------------------------------------------------------------------------

def pv_fix_calibration(intrinsics, extrinsics):
    R = np.array([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, -1, 0], [0, 0, 0, 1]], dtype=extrinsics.dtype)
    intrinsics[0, 0] = -intrinsics[0, 0]
    extrinsics = extrinsics @ R
    return (intrinsics, extrinsics)


#------------------------------------------------------------------------------
# SM
#------------------------------------------------------------------------------

def sm_mesh_cast(mesh, vertex_positions_type, triangle_indices_type, vertex_normals_type):
    mesh.vertex_positions = mesh.vertex_positions.astype(vertex_positions_type)
    mesh.triangle_indices = mesh.triangle_indices.astype(triangle_indices_type)
    mesh.vertex_normals   = mesh.vertex_normals.astype(vertex_normals_type)


def sm_mesh_normalize_positions(mesh):
    mesh.vertex_positions[:, 0:3] *= mesh.vertex_position_scale
    mesh.vertex_positions = (mesh.vertex_positions / mesh.vertex_positions[:, 3:]) @ mesh.pose


def sm_mesh_normalize_normals(mesh):
    d = np.linalg.norm(mesh.vertex_normals, axis=1)
    mesh.vertex_normals[d > 0, :] = mesh.vertex_normals[d > 0, :] / d[d > 0, np.newaxis]
    mesh.vertex_normals = mesh.vertex_normals @ mesh.pose


def sm_mesh_normalize(mesh):
    sm_mesh_normalize_positions(mesh)
    sm_mesh_normalize_normals(mesh)


def sm_mesh_to_open3d_triangle_mesh(mesh):
    open3d_mesh = o3d.geometry.TriangleMesh()

    open3d_mesh.vertices       = o3d.utility.Vector3dVector(mesh.vertex_positions[:, 0:3])
    open3d_mesh.vertex_normals = o3d.utility.Vector3dVector(mesh.vertex_normals[:, 0:3])
    open3d_mesh.triangles      = o3d.utility.Vector3iVector(mesh.triangle_indices)

    return open3d_mesh


class _sm_manager_entry:
    def __init__(self, update_time, mesh, rcs):
        self.update_time = update_time
        self.mesh = mesh
        self.rcs = rcs


class sm_manager:
    def __init__(self, host, triangles_per_cubic_meter, threads):
        self._tpcm = triangles_per_cubic_meter
        self._threads = threads
        self._vpf = hl2ss.SM_VertexPositionFormat.R16G16B16A16IntNormalized
        self._tif = hl2ss.SM_TriangleIndexFormat.R16UInt
        self._vnf = hl2ss.SM_VertexNormalFormat.R8G8B8A8IntNormalized
        self._normals = False
        self._bounds = False
        self._ipc = hl2ss.ipc_sm(host, hl2ss.IPCPort.SPATIAL_MAPPING)
        self._surfaces = {}

    def open(self):
        self._ipc.open()

    def close(self):
        self._ipc.close()

    def create_observer(self):
        self._ipc.create_observer()

    def set_volumes(self, volumes):
        self._ipc.set_volumes(volumes)

    def update(self):
        surfaces = {}
        tasks = hl2ss.sm_mesh_task()        
        updated_surfaces = []
        
        for surface_info in self._ipc.get_observed_surfaces():
            id = surface_info.id
            surface_info.id = surface_info.id.hex()
            if (surface_info.id in self._surfaces):
                previous_entry = self._surfaces[surface_info.id]
                if (surface_info.update_time <= previous_entry.update_time):
                    surfaces[surface_info.id] = previous_entry
                    continue
            tasks.add_task(id, self._tpcm, self._vpf, self._tif, self._vnf, self._normals, self._bounds)
            updated_surfaces.append(surface_info)

        count = len(updated_surfaces)
        if (count <= 0):
            return count

        for index, mesh in self._ipc.get_meshes(tasks, self._threads).items():
            if (mesh is None):
                continue
            mesh.unpack(self._vpf, self._tif, self._vnf)
            sm_mesh_cast(mesh, np.float64, np.uint32, np.float64)
            sm_mesh_normalize(mesh)
            rcs = o3d.t.geometry.RaycastingScene()
            rcs.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(sm_mesh_to_open3d_triangle_mesh(mesh)))
            surface_info = updated_surfaces[index]
            surfaces[surface_info.id] = _sm_manager_entry(surface_info.update_time, mesh, rcs)

        self._surfaces = surfaces
        return count

    def cast_rays(self, rays):
        distances = np.zeros(rays.shape[0:-1] + (len(self._surfaces),))
        for index, entry in enumerate(self._surfaces.values()):
            distances[..., index] = entry.rcs.cast_rays(rays)['t_hit'].numpy()
        distances = np.min(distances, axis=-1)
        return distances


#------------------------------------------------------------------------------
# Calibration
#------------------------------------------------------------------------------

def _save_calibration_rm_vlc(calibration, path):
    calibration.uv2xy                .tofile(os.path.join(path, 'uv2xy.bin'))
    calibration.extrinsics           .tofile(os.path.join(path, 'extrinsics.bin'))
    calibration.undistort_map        .tofile(os.path.join(path, 'undistort_map.bin'))
    calibration.intrinsics           .tofile(os.path.join(path, 'intrinsics.bin'))


def _save_calibration_rm_depth_ahat(calibration, path):
    calibration.uv2xy                .tofile(os.path.join(path, 'uv2xy.bin'))
    calibration.extrinsics           .tofile(os.path.join(path, 'extrinsics.bin'))
    calibration.scale                .tofile(os.path.join(path, 'scale.bin'))
    calibration.alias                .tofile(os.path.join(path, 'alias.bin'))
    calibration.undistort_map        .tofile(os.path.join(path, 'undistort_map.bin'))
    calibration.intrinsics           .tofile(os.path.join(path, 'intrinsics.bin'))


def _save_calibration_rm_depth_longthrow(calibration, path):
    calibration.uv2xy                .tofile(os.path.join(path, 'uv2xy.bin'))
    calibration.extrinsics           .tofile(os.path.join(path, 'extrinsics.bin'))
    calibration.scale                .tofile(os.path.join(path, 'scale.bin'))
    calibration.undistort_map        .tofile(os.path.join(path, 'undistort_map.bin'))
    calibration.intrinsics           .tofile(os.path.join(path, 'intrinsics.bin'))


def _save_calibration_rm_imu(calibration, path):
    calibration.extrinsics           .tofile(os.path.join(path, 'extrinsics.bin'))


def _save_calibration_pv(calibration, path):
    calibration.focal_length         .tofile(os.path.join(path, 'focal_length.bin'))
    calibration.principal_point      .tofile(os.path.join(path, 'principal_point.bin'))
    calibration.radial_distortion    .tofile(os.path.join(path, 'radial_distortion.bin'))
    calibration.tangential_distortion.tofile(os.path.join(path, 'tangential_distortion.bin'))
    calibration.projection           .tofile(os.path.join(path, 'projection.bin'))
    calibration.intrinsics           .tofile(os.path.join(path, 'intrinsics.bin'))


def _save_extrinsics_pv(extrinsics, path):
    extrinsics                       .tofile(os.path.join(path, 'extrinsics.bin'))


def _load_calibration_rm_vlc(path):
    lut_shape = hl2ss.Parameters_RM_VLC.SHAPE + (2,)

    uv2xy                 = np.fromfile(os.path.join(path, 'uv2xy.bin'),                 dtype=np.float32).reshape(lut_shape)
    extrinsics            = np.fromfile(os.path.join(path, 'extrinsics.bin'),            dtype=np.float32).reshape((4, 4))
    undistort_map         = np.fromfile(os.path.join(path, 'undistort_map.bin'),         dtype=np.float32).reshape(lut_shape)
    intrinsics            = np.fromfile(os.path.join(path, 'intrinsics.bin'),            dtype=np.float32).reshape((4, 4))

    return hl2ss._Mode2_RM_VLC(uv2xy, extrinsics, undistort_map, intrinsics)


def _load_calibration_rm_depth_ahat(path):
    lut_shape = hl2ss.Parameters_RM_DEPTH_AHAT.SHAPE + (2,)

    uv2xy                 = np.fromfile(os.path.join(path, 'uv2xy.bin'),                 dtype=np.float32).reshape(lut_shape)
    extrinsics            = np.fromfile(os.path.join(path, 'extrinsics.bin'),            dtype=np.float32).reshape((4, 4))
    scale                 = np.fromfile(os.path.join(path, 'scale.bin'),                 dtype=np.float32)
    alias                 = np.fromfile(os.path.join(path, 'alias.bin'),                 dtype=np.float32)
    undistort_map         = np.fromfile(os.path.join(path, 'undistort_map.bin'),         dtype=np.float32).reshape(lut_shape)
    intrinsics            = np.fromfile(os.path.join(path, 'intrinsics.bin'),            dtype=np.float32).reshape((4, 4))

    return hl2ss._Mode2_RM_DEPTH_AHAT(uv2xy, extrinsics, scale, alias, undistort_map, intrinsics)


def _load_calibration_rm_depth_longthrow(path):
    lut_shape = hl2ss.Parameters_RM_DEPTH_LONGTHROW.SHAPE + (2,)

    uv2xy                 = np.fromfile(os.path.join(path, 'uv2xy.bin'),                 dtype=np.float32).reshape(lut_shape)
    extrinsics            = np.fromfile(os.path.join(path, 'extrinsics.bin'),            dtype=np.float32).reshape((4, 4))
    scale                 = np.fromfile(os.path.join(path, 'scale.bin'),                 dtype=np.float32)
    undistort_map         = np.fromfile(os.path.join(path, 'undistort_map.bin'),         dtype=np.float32).reshape(lut_shape)
    intrinsics            = np.fromfile(os.path.join(path, 'intrinsics.bin'),            dtype=np.float32).reshape((4, 4))

    return hl2ss._Mode2_RM_DEPTH_LONGTHROW(uv2xy, extrinsics, scale, undistort_map, intrinsics)


def _load_calibration_rm_imu(path):
    extrinsics            = np.fromfile(os.path.join(path, 'extrinsics.bin'),            dtype=np.float32).reshape((4, 4))

    return hl2ss._Mode2_RM_IMU(extrinsics)


def _load_calibration_pv(path):
    focal_length          = np.fromfile(os.path.join(path, 'focal_length.bin'),          dtype=np.float32)
    principal_point       = np.fromfile(os.path.join(path, 'principal_point.bin'),       dtype=np.float32)
    radial_distortion     = np.fromfile(os.path.join(path, 'radial_distortion.bin'),     dtype=np.float32)
    tangential_distortion = np.fromfile(os.path.join(path, 'tangential_distortion.bin'), dtype=np.float32)
    projection            = np.fromfile(os.path.join(path, 'projection.bin'),            dtype=np.float32).reshape((4, 4))
    intrinsics            = np.fromfile(os.path.join(path, 'intrinsics.bin'),            dtype=np.float32).reshape((4, 4))

    return hl2ss._Mode2_PV(focal_length, principal_point, radial_distortion, tangential_distortion, projection, intrinsics)


def _load_extrinsics_pv(path):
    extrinsics            = np.fromfile(os.path.join(path, 'extrinsics.bin'),            dtype=np.float32).reshape((4, 4))

    return extrinsics


#------------------------------------------------------------------------------
# Calibration Wrappers
#------------------------------------------------------------------------------

def _download_calibration_rm(host, port):
    if (port == hl2ss.StreamPort.RM_VLC_LEFTFRONT):
        return hl2ss.download_calibration_rm_vlc(            host, port)
    if (port == hl2ss.StreamPort.RM_VLC_LEFTLEFT):
        return hl2ss.download_calibration_rm_vlc(            host, port)
    if (port == hl2ss.StreamPort.RM_VLC_RIGHTFRONT):
        return hl2ss.download_calibration_rm_vlc(            host, port)
    if (port == hl2ss.StreamPort.RM_VLC_RIGHTRIGHT):
        return hl2ss.download_calibration_rm_vlc(            host, port)
    if (port == hl2ss.StreamPort.RM_DEPTH_AHAT):
        return hl2ss.download_calibration_rm_depth_ahat(     host, port)
    if (port == hl2ss.StreamPort.RM_DEPTH_LONGTHROW):
        return hl2ss.download_calibration_rm_depth_longthrow(host, port)
    if (port == hl2ss.StreamPort.RM_IMU_ACCELEROMETER):
        return hl2ss.download_calibration_rm_imu(            host, port)
    if (port == hl2ss.StreamPort.RM_IMU_GYROSCOPE):
        return hl2ss.download_calibration_rm_imu(            host, port)


def _save_calibration_rm(port, calibration, path):
    if (port == hl2ss.StreamPort.RM_VLC_LEFTFRONT):
        return _save_calibration_rm_vlc(            calibration, path)
    if (port == hl2ss.StreamPort.RM_VLC_LEFTLEFT):
        return _save_calibration_rm_vlc(            calibration, path)
    if (port == hl2ss.StreamPort.RM_VLC_RIGHTFRONT):
        return _save_calibration_rm_vlc(            calibration, path)
    if (port == hl2ss.StreamPort.RM_VLC_RIGHTRIGHT):
        return _save_calibration_rm_vlc(            calibration, path)
    if (port == hl2ss.StreamPort.RM_DEPTH_AHAT):
        return _save_calibration_rm_depth_ahat(     calibration, path)
    if (port == hl2ss.StreamPort.RM_DEPTH_LONGTHROW):
        return _save_calibration_rm_depth_longthrow(calibration, path)
    if (port == hl2ss.StreamPort.RM_IMU_ACCELEROMETER):
        return _save_calibration_rm_imu(            calibration, path)
    if (port == hl2ss.StreamPort.RM_IMU_GYROSCOPE):
        return _save_calibration_rm_imu(            calibration, path)

    return None


def _load_calibration_rm(port, path):   
    if (port == hl2ss.StreamPort.RM_VLC_LEFTFRONT):
        return _load_calibration_rm_vlc(            path)
    if (port == hl2ss.StreamPort.RM_VLC_LEFTLEFT):
        return _load_calibration_rm_vlc(            path)
    if (port == hl2ss.StreamPort.RM_VLC_RIGHTFRONT):
        return _load_calibration_rm_vlc(            path)
    if (port == hl2ss.StreamPort.RM_VLC_RIGHTRIGHT):
        return _load_calibration_rm_vlc(            path)
    if (port == hl2ss.StreamPort.RM_DEPTH_AHAT):
        return _load_calibration_rm_depth_ahat(     path)
    if (port == hl2ss.StreamPort.RM_DEPTH_LONGTHROW):
        return _load_calibration_rm_depth_longthrow(path)
    if (port == hl2ss.StreamPort.RM_IMU_ACCELEROMETER):
        return _load_calibration_rm_imu(            path)
    if (port == hl2ss.StreamPort.RM_IMU_GYROSCOPE):
        return _load_calibration_rm_imu(            path)

    return None


#------------------------------------------------------------------------------
# Calibration Manager
#------------------------------------------------------------------------------

class _Mode2_PV(hl2ss._Mode2_PV):
    def __init__(self, mode2, extrinsics):
        super().__init__(mode2.focal_length, mode2.principal_point, mode2.radial_distortion, mode2.tangential_distortion, mode2.projection, mode2.intrinsics)
        self.extrinsics = extrinsics


def _check_calibration_directory(path):
    if (not os.path.isdir(path)):
        raise IOError('Calibration path ' + path + ' does not exist')


def _calibration_subdirectory(port, path):
    return os.path.join(path, hl2ss.get_port_name(port))


def _calibration_subdirectory_pv(focus, width, height, path):
    return os.path.join(path, '{focus}_{width}_{height}'.format(focus=int(focus), width=int(width), height=int(height)))


def get_calibration_rm(host, port, path):
    _check_calibration_directory(path)

    base = _calibration_subdirectory(port, path)

    try:
        calibration = _load_calibration_rm(port, base)
    except:
        calibration = _download_calibration_rm(host, port)
        os.makedirs(base, exist_ok=True)
        _save_calibration_rm(port, calibration, base)

    return calibration


def get_calibration_pv(host, port, path, focus, width, height, framerate, load_extrinsics):
    _check_calibration_directory(path)

    root = _calibration_subdirectory(port, path)
    base = _calibration_subdirectory_pv(focus, width, height, root)
    extrinsics = _load_extrinsics_pv(root) if (load_extrinsics) else None

    try:
        calibration = _load_calibration_pv(base)
    except:
        calibration = hl2ss.download_calibration_pv(host, port, width, height, framerate)
        os.makedirs(base, exist_ok=True)
        _save_calibration_pv(calibration, base)
        
    return _Mode2_PV(calibration, extrinsics)


def save_extrinsics_pv(port, extrinsics, path):
    _check_calibration_directory(path)

    base = _calibration_subdirectory(port, path)
    os.makedirs(base, exist_ok=True)

    return _save_extrinsics_pv(extrinsics, base)


#------------------------------------------------------------------------------
# Stereo Calibration / Rectification
#------------------------------------------------------------------------------

class StereoCalibration:
    def __init__(self, R, t, E, F):
        self.R = R
        self.t = t
        self.E = E
        self.F = F


class StereoRectification:
    def __init__(self, R1, R2, P1, P2, Q, roi1, roi2, map1, map2):
        self.R1   = R1
        self.R2   = R2
        self.P1   = P1
        self.P2   = P2
        self.Q    = Q
        self.roi1 = roi1
        self.roi2 = roi2
        self.map1 = map1
        self.map2 = map2


def rm_vlc_stereo_calibrate(intrinsics_1, intrinsics_2, extrinsics_1, extrinsics_2):
    extrinsics = camera_to_rignode(extrinsics_1) @ rignode_to_camera(extrinsics_2)
    R, t = extrinsics_to_Rt(extrinsics)
    t_skew = vector_to_skew_symmetric(t)
    E = Rt_to_essential(R, t_skew)
    F = essential_to_fundamental(image_to_camera(intrinsics_1)[:3, :3], image_to_camera(intrinsics_2)[:3, :3], E)

    return StereoCalibration(R, t, E, F)


def rm_vlc_stereo_rectify(intrinsics_1, intrinsics_2, R_1_to_2, t_1_to_2, image_shape):
    K_1 = intrinsics_1[:3, :3].astype(np.float64).transpose()
    K_2 = intrinsics_2[:3, :3].astype(np.float64).transpose()
    R   = R_1_to_2.astype(np.float64).transpose()
    t   = t_1_to_2.astype(np.float64).reshape((3, 1))

    R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(K_1, None, K_2, None, image_shape, R, t)

    map1x, map1y = cv2.initUndistortRectifyMap(K_1, None, R1, P1, image_shape, cv2.CV_32FC1)
    map2x, map2y = cv2.initUndistortRectifyMap(K_2, None, R2, P2, image_shape, cv2.CV_32FC1)

    roi1 = np.array(roi1, dtype=np.int32)
    roi2 = np.array(roi2, dtype=np.int32)

    return StereoRectification(R1, R2, P1, P2, Q, roi1, roi2, np.dstack((map1x, map1y)), np.dstack((map2x, map2y))) # float64, opencv shape


def _stereo_subdirectory(port_1, port_2, path):
    name_1 = hl2ss.get_port_name(port_1)
    name_2 = hl2ss.get_port_name(port_2)
    return os.path.join(path, name_1 + '.' + name_2)


def _save_stereo_calibration(calibration, path):
    calibration.R     .tofile(os.path.join(path, 'R.bin'))
    calibration.t     .tofile(os.path.join(path, 't.bin'))
    calibration.E     .tofile(os.path.join(path, 'E.bin'))
    calibration.F     .tofile(os.path.join(path, 'F.bin'))


def _save_stereo_rectification(rectification, path):
    rectification.R1  .tofile(os.path.join(path, 'R1.bin'))
    rectification.R2  .tofile(os.path.join(path, 'R2.bin'))
    rectification.P1  .tofile(os.path.join(path, 'P1.bin'))
    rectification.P2  .tofile(os.path.join(path, 'P2.bin'))
    rectification.Q   .tofile(os.path.join(path, 'Q.bin'))
    rectification.roi1.tofile(os.path.join(path, 'roi1.bin'))
    rectification.roi2.tofile(os.path.join(path, 'roi2.bin'))
    rectification.map1.tofile(os.path.join(path, 'map1.bin'))
    rectification.map2.tofile(os.path.join(path, 'map2.bin'))


def _load_stereo_calibration(path):
    R    = np.fromfile(os.path.join(path, 'R.bin'),    dtype=np.float32).reshape((3, 3))
    t    = np.fromfile(os.path.join(path, 't.bin'),    dtype=np.float32).reshape((1, 3))
    E    = np.fromfile(os.path.join(path, 'E.bin'),    dtype=np.float32).reshape((3, 3))
    F    = np.fromfile(os.path.join(path, 'F.bin'),    dtype=np.float32).reshape((3, 3))

    return StereoCalibration(R, t, E, F)


def _load_stereo_rectification(map_shape, path):
    lut_shape = map_shape + (2,)

    R1   = np.fromfile(os.path.join(path, 'R1.bin'),   dtype=np.float64).reshape((3, 3))
    R2   = np.fromfile(os.path.join(path, 'R2.bin'),   dtype=np.float64).reshape((3, 3))
    P1   = np.fromfile(os.path.join(path, 'P1.bin'),   dtype=np.float64).reshape((3, 4))
    P2   = np.fromfile(os.path.join(path, 'P2.bin'),   dtype=np.float64).reshape((3, 4))
    Q    = np.fromfile(os.path.join(path, 'Q.bin'),    dtype=np.float64).reshape((4, 4))
    roi1 = np.fromfile(os.path.join(path, 'roi1.bin'), dtype=np.int32)
    roi2 = np.fromfile(os.path.join(path, 'roi2.bin'), dtype=np.int32)
    map1 = np.fromfile(os.path.join(path, 'map1.bin'), dtype=np.float32).reshape(lut_shape)
    map2 = np.fromfile(os.path.join(path, 'map2.bin'), dtype=np.float32).reshape(lut_shape)

    return StereoRectification(R1, R2, P1, P2, Q, roi1, roi2, map1, map2)


def save_stereo_calibration(port_1, port_2, calibration, path):
    _check_calibration_directory(path)
    base = _stereo_subdirectory(port_1, port_2, path)
    os.makedirs(base, exist_ok=True)
    return _save_stereo_calibration(calibration, base)
    

def save_stereo_rectification(port_1, port_2, rectification, path):
    _check_calibration_directory(path)
    base = _stereo_subdirectory(port_1, port_2, path)
    os.makedirs(base, exist_ok=True)
    return _save_stereo_rectification(rectification, base)


def load_stereo_calibration(port_1, port_2, path):
    _check_calibration_directory(path)
    base = _stereo_subdirectory(port_1, port_2, path)
    return _load_stereo_calibration(base)


def load_stereo_rectification(port_1, port_2, path, map_shape):
    _check_calibration_directory(path)
    base = _stereo_subdirectory(port_1, port_2, path)
    return _load_stereo_rectification(map_shape, base)

