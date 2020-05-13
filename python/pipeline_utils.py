import cv2
import numpy as np
import exifread
import rawpy
from exifread import Ratio
from scipy.io import loadmat


def get_visible_raw_image(image_path):
    raw_image = rawpy.imread(image_path).raw_image_visible.copy()
    # raw_image = rawpy.imread(image_path).raw_image.copy()
    return raw_image


def get_image_tags(image_path):
    f = open(image_path, 'rb')
    tags = exifread.process_file(f)
    return tags


def get_metadata(image_path):
    metadata = {}
    tags = get_image_tags(image_path)
    metadata['linearization_table'] = get_linearization_table(tags)
    metadata['black_level'] = get_black_level(tags)
    metadata['white_level'] = get_white_level(tags)
    metadata['cfa_pattern'] = get_cfa_pattern(tags)
    metadata['as_shot_neutral'] = get_as_shot_neutral(tags)
    color_matrix_1, color_matrix_2 = get_color_matrices(tags)
    metadata['color_matrix_1'] = color_matrix_1
    metadata['color_matrix_2'] = color_matrix_2
    metadata['orientation'] = get_orientation(tags)
    # ...
    # fall back to default values, if necessary
    if metadata['black_level'] is None:
        metadata['black_level'] = 0
        print("Black level is None; using 0.")
    if metadata['white_level'] is None:
        metadata['white_level'] = 2 ** 16
        print("White level is None; using 2 ** 16.")
    if metadata['cfa_pattern'] is None:
        metadata['cfa_pattern'] = [0, 1, 1, 2]
        print("CFAPattern is None; using [0, 1, 1, 2] (RGGB)")
    if metadata['as_shot_neutral'] is None:
        metadata['as_shot_neutral'] = [1, 1, 1]
        print("AsShotNeutral is None; using [1, 1, 1]")
    if metadata['color_matrix_1'] is None:
        metadata['color_matrix_1'] = [1] * 9
        print("ColorMatrix1 is None; using [1, 1, 1, 1, 1, 1, 1, 1, 1]")
    if metadata['color_matrix_2'] is None:
        metadata['color_matrix_2'] = [1] * 9
        print("ColorMatrix2 is None; using [1, 1, 1, 1, 1, 1, 1, 1, 1]")
    if metadata['orientation'] is None:
        metadata['orientation'] = 0
        print("Orientation is None; using 0.")
    # ...
    return metadata


def get_linearization_table(tags):
    possible_keys = ['Image Tag 0xC618', 'Image Tag 50712', 'LinearizationTable', 'Image LinearizationTable']
    return get_values(tags, possible_keys)


def get_black_level(tags):
    possible_keys = ['Image Tag 0xC61A', 'Image Tag 50714', 'BlackLevel', 'Image BlackLevel']
    return get_values(tags, possible_keys)


def get_white_level(tags):
    possible_keys = ['Image Tag 0xC61D', 'Image Tag 50717', 'WhiteLevel', 'Image WhiteLevel']
    return get_values(tags, possible_keys)


def get_cfa_pattern(tags):
    possible_keys = ['CFAPattern', 'Image CFAPattern']
    return get_values(tags, possible_keys)


def get_as_shot_neutral(tags):
    possible_keys = ['Image Tag 0xC628', 'Image Tag 50728', 'AsShotNeutral', 'Image AsShotNeutral']
    return get_values(tags, possible_keys)


def get_color_matrices(tags):
    possible_keys_1 = ['Image Tag 0xC621', 'Image Tag 50721', 'ColorMatrix1', 'Image ColorMatrix1']
    color_matrix_1 = get_values(tags, possible_keys_1)
    possible_keys_2 = ['Image Tag 0xC622', 'Image Tag 50722', 'ColorMatrix2', 'Image ColorMatrix2']
    color_matrix_2 = get_values(tags, possible_keys_2)
    return color_matrix_1, color_matrix_2


def get_orientation(tags):
    possible_tags = ['Orientation', 'Image Orientation']
    return get_values(tags, possible_tags)


def get_values(tags, possible_keys):
    values = None
    for key in possible_keys:
        if key in tags.keys():
            values = tags[key].values
    return values


def normalize(raw_image, black_level, white_level):
    black_level_mask = black_level
    if len(black_level) == 4:
        if type(black_level[0]) is Ratio:
            black_level = ratios2floats(black_level)
        black_level_mask = np.zeros(raw_image.shape)
        idx2by2 = [[0, 0], [0, 1], [1, 0], [1, 1]]
        step2 = 2
        for i, idx in enumerate(idx2by2):
            black_level_mask[idx[0]::step2, idx[1]::step2] = black_level[i]
    normalized_image = (raw_image - black_level_mask) / (white_level - black_level_mask)
    return normalized_image


def ratios2floats(ratios):
    floats = []
    for ratio in ratios:
        floats.append(float(ratio.num) / ratio.den)
    return floats


def white_balance(normalized_image, as_shot_neutral, cfa_pattern):
    if type(as_shot_neutral[0]) is Ratio:
        as_shot_neutral = ratios2floats(as_shot_neutral)
    idx2by2 = [[0, 0], [0, 1], [1, 0], [1, 1]]
    step2 = 2
    white_balanced_image = np.zeros(normalized_image.shape)
    for i, idx in enumerate(idx2by2):
        idx_y = idx[0]
        idx_x = idx[1]
        white_balanced_image[idx_y::step2, idx_x::step2] = \
            normalized_image[idx_y::step2, idx_x::step2] / as_shot_neutral[cfa_pattern[i]]
    white_balanced_image = np.clip(white_balanced_image, 0.0, 1.0)
    return white_balanced_image


def get_opencv_demsaic_flag(cfa_pattern, output_channel_order):
    # using opencv edge-aware demosaicing
    if output_channel_order == 'BGR':
        if cfa_pattern == [0, 1, 1, 2]:  # RGGB
            opencv_demosaic_flag = cv2.COLOR_BAYER_BG2BGR_EA
        elif cfa_pattern == [2, 1, 1, 0]:  # BGGR
            opencv_demosaic_flag = cv2.COLOR_BAYER_RG2BGR_EA
        elif cfa_pattern == [1, 0, 2, 1]:  # GRBG
            opencv_demosaic_flag = cv2.COLOR_BAYER_GB2BGR_EA
        elif cfa_pattern == [1, 2, 0, 1]:  # GBRG
            opencv_demosaic_flag = cv2.COLOR_BAYER_GR2BGR_EA
        else:
            opencv_demosaic_flag = cv2.COLOR_BAYER_BG2BGR_EA
            print("CFA pattern not identified.")
    else:  # RGB
        if cfa_pattern == [0, 1, 1, 2]:  # RGGB
            opencv_demosaic_flag = cv2.COLOR_BAYER_BG2RGB_EA
        elif cfa_pattern == [2, 1, 1, 0]:  # BGGR
            opencv_demosaic_flag = cv2.COLOR_BAYER_RG2RGB_EA
        elif cfa_pattern == [1, 0, 2, 1]:  # GRBG
            opencv_demosaic_flag = cv2.COLOR_BAYER_GB2RGB_EA
        elif cfa_pattern == [1, 2, 0, 1]:  # GBRG
            opencv_demosaic_flag = cv2.COLOR_BAYER_GR2RGB_EA
        else:
            opencv_demosaic_flag = cv2.COLOR_BAYER_BG2RGB_EA
            print("CFA pattern not identified.")
    return opencv_demosaic_flag


def demosaic(white_balanced_image, cfa_pattern, output_channel_order='BGR'):
    opencv_demosaic_flag = get_opencv_demsaic_flag(cfa_pattern, output_channel_order)
    max_val = 16383
    demosaiced_image = cv2.cvtColor((white_balanced_image * max_val).astype(dtype=np.uint16), opencv_demosaic_flag)
    demosaiced_image = demosaiced_image.astype(dtype=np.float32) / max_val
    return demosaiced_image


def apply_color_space_transform(demosaiced_image, color_matrix_1, color_matrix_2):
    if type(color_matrix_1[0]) is Ratio:
        color_matrix_1 = ratios2floats(color_matrix_1)
    if type(color_matrix_2[0]) is Ratio:
        color_matrix_2 = ratios2floats(color_matrix_2)
    xyz2cam1 = np.reshape(np.asarray(color_matrix_1), (3, 3))
    xyz2cam2 = np.reshape(np.asarray(color_matrix_2), (3, 3))
    # normalize rows (needed?)
    xyz2cam1 = xyz2cam1 / np.sum(xyz2cam1, axis=1, keepdims=True)
    xyz2cam2 = xyz2cam2 / np.sum(xyz2cam1, axis=1, keepdims=True)
    # inverse
    cam2xyz1 = np.linalg.inv(xyz2cam1)
    cam2xyz2 = np.linalg.inv(xyz2cam2)
    # for now, use one matrix  # TODO: interpolate btween both
    # simplified matrix multiplication
    xyz_image = cam2xyz1[np.newaxis, np.newaxis, :, :] * demosaiced_image[:, :, np.newaxis, :]
    xyz_image = np.sum(xyz_image, axis=-1)
    xyz_image = np.clip(xyz_image, 0.0, 1.0)
    return xyz_image


def transform_xyz_to_srgb(xyz_image):
    # srgb2xyz = np.array([[0.4124564, 0.3575761, 0.1804375],
    #                      [0.2126729, 0.7151522, 0.0721750],
    #                      [0.0193339, 0.1191920, 0.9503041]])

    # xyz2srgb = np.linalg.inv(srgb2xyz)

    xyz2srgb = np.array([[3.2404542, -1.5371385, -0.4985314],
                         [-0.9692660, 1.8760108, 0.0415560],
                         [0.0556434, -0.2040259, 1.0572252]])

    # normalize rows (needed?)
    xyz2srgb = xyz2srgb / np.sum(xyz2srgb, axis=-1, keepdims=True)

    srgb_image = xyz2srgb[np.newaxis, np.newaxis, :, :] * xyz_image[:, :, np.newaxis, :]
    srgb_image = np.sum(srgb_image, axis=-1)
    srgb_image = np.clip(srgb_image, 0.0, 1.0)
    return srgb_image


def fix_orientation(image, orientation):
    # 1 = Horizontal(normal)
    # 2 = Mirror horizontal
    # 3 = Rotate 180
    # 4 = Mirror vertical
    # 5 = Mirror horizontal and rotate 270 CW
    # 6 = Rotate 90 CW
    # 7 = Mirror horizontal and rotate 90 CW
    # 8 = Rotate 270 CW

    if type(orientation) is list:
        orientation = orientation[0]

    if orientation == 1:
        pass
    elif orientation == 2:
        image = cv2.flip(image, 0)
    elif orientation == 3:
        image = cv2.rotate(image, cv2.ROTATE_180)
    elif orientation == 4:
        image = cv2.flip(image, 1)
    elif orientation == 5:
        image = cv2.flip(image, 0)
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    elif orientation == 6:
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif orientation == 7:
        image = cv2.flip(image, 0)
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif orientation == 8:
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)

    return image


def apply_gamma(x):
    return x ** (1.0 / 2.2)


def apply_tone_map(x):
    # simple tone curve
    # return 3 * x ** 2 - 2 * x ** 3

    tone_curve = loadmat('tone_curve.mat')
    tone_curve = tone_curve['tc']
    x = np.round(x * (len(tone_curve) - 1)).astype(int)
    tone_mapped_image = np.squeeze(tone_curve[x])
    return tone_mapped_image
