#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Code originates from:
        http://docs.opencv.org/trunk/doc/py_tutorials/py_calib3d/py_calibration/py_calibration.html
    
    View demo video at http://www.youtube.com/watch?v=SX2qodUfDaA
"""
import os
from math import degrees
import numpy as np
import quaternions as qwts
import cv2
import cv2_helpers as cvh
from cv2_helpers import rgb, format3DVector



def prepare_object_points(boardSize):
    """
    Prepare object points, like (0,0,0), (0,1,0), (0,2,0) ... ,(5,7,0).
    """
    objp = np.zeros((np.prod(boardSize), 3), np.float32)
    objp[:,:] = np.array([ map(float, [i, j, 0])
                            for i in range(boardSize[1])
                            for j in range(boardSize[0]) ])
    
    return objp


def calibrate_camera_interactive(images, objp, boardSize):
    # Arrays to store object points and image points from all the images.
    objectPoints = []    # 3d point in real world space
    imagePoints = []    # 2d points in image plane

    test_image = cv2.imread(images[0])
    imageSize = (test_image.shape[1], test_image.shape[0])

    # Read images
    for fname in images:
        img = cv2.imread(fname)
        ret, corners = cvh.extractChessboardFeatures(img, boardSize)

        # If chessboard corners are found, add object points and image points
        if ret == True:
            objectPoints.append(objp)
            imagePoints.append(corners)

            # Draw and display the corners
            cv2.drawChessboardCorners(
                    img, boardSize, corners, ret )
            cv2.imshow("img", img)
            cv2.waitKey(100)

    # Calibration
    reproj_error, cameraMatrix, distCoeffs, rvecs, tvecs = cv2.calibrateCamera(
            objectPoints, imagePoints, imageSize )
    distCoeffs = distCoeffs.reshape((-1))    # convert to vector
    
    return reproj_error, cameraMatrix, distCoeffs, rvecs, tvecs, \
            objectPoints, imagePoints, imageSize


def save_camera_intrinsics(filename, cameraMatrix, distCoeffs, imageSize):
    out = """\
    # cameraMatrix, distCoeffs, imageSize =
    
    %s, \\
    \\
    %s, \\
    \\
    %s
    """
    from textwrap import dedent
    out = dedent(out) % (repr(cameraMatrix), repr(distCoeffs), repr(imageSize))
    open(filename, 'w').write(out)

def load_camera_intrinsics(filename):
    from numpy import array
    cameraMatrix, distCoeffs, imageSize = \
            eval(open(filename, 'r').read())
    return cameraMatrix, distCoeffs, imageSize


def undistort_image(img, cameraMatrix, distCoeffs, imageSize):
    # Refine cameraMatrix, and calculate ReqionOfInterest
    cameraMatrix_new, roi = cv2.getOptimalNewCameraMatrix(
            cameraMatrix, distCoeffs, imageSize,
            1 )    # all source image pixels retained in undistorted image

    # undistort
    mapX, mapY = cv2.initUndistortRectifyMap(
            cameraMatrix, distCoeffs,
            None,    # optional rectification transformation
            cameraMatrix_new, imageSize,
            5 )    # type of the first output map (CV_32FC1)
    img_undistorted = cv2.remap(
            img, mapX, mapY, cv2.INTER_LINEAR )

    # crop the image
    x,y, w,h = roi
    img_undistorted = img_undistorted[y:y+h, x:x+w]
    
    return img_undistorted, roi


def reprojection_error(cameraMatrix, distCoeffs, rvecs, tvecs, objectPoints, imagePoints, boardSize):
    mean_error = np.zeros((1, 2))
    square_error = np.zeros((1, 2))
    n_images = len(imagePoints)

    for i in xrange(n_images):
        imgp_reproj, jacob = cv2.projectPoints(
                objectPoints[i], rvecs[i], tvecs[i], cameraMatrix, distCoeffs )
        error = imgp_reproj.reshape(-1, 2) - imagePoints[i]
        mean_error += abs(error).sum(axis=0) / np.prod(boardSize)
        square_error += (error**2).sum(axis=0) / np.prod(boardSize)

    mean_error = cv2.norm(mean_error / n_images)
    square_error = np.sqrt(square_error.sum() / n_images)
    
    return mean_error, square_error


# Initialize consts or tmp vars to be used in linear_LS_triangulation()
linear_LS_triangulation_c = -np.eye(2, 3)
linear_LS_triangulation_A = np.zeros((4, 3))
linear_LS_triangulation_b = np.zeros((4, 1))

def linear_LS_triangulation(u, P, K_inv, u1, P1, K1_inv):
    """
    Linear Least Squares based triangulation.
    WARNING: image distortion is not compensated (?)
    TODO: flip rows and columns to increase performance (improve for cache)
    
    (u, P) is the reference pair containing (non-homogenous) image points and the corresponding camera matrix.
    (u1, P1) is the second pair.
    K_inv and K1_inv are the corresponding inverse camera calibration matrices.
    
    u and u1 are matrices: amount of points equals #columns and should be equal for u and u1.
    """
    global linear_LS_triangulation_A, linear_LS_triangulation_b
    
    # Create a temporary matrix to represent u and u1 in homogenous coordinates
    ux_homogenous = np.zeros((3, u.shape[1]))
    ux_homogenous[2, :] = 1
    
    # Normalize image points
    ux_homogenous[0:2, :] = u
    u_normalized = K_inv[0:2, :].dot(ux_homogenous)
    ux_homogenous[0:2, :] = u1
    u1_normalized = K1_inv[0:2, :].dot(ux_homogenous)
    
    # Create array of triangulated points
    x = np.zeros((3, u.shape[1]))
    
    for i in range(u.shape[1]):
        # Build C matrices, to visualize calculation structure
        C = np.array(linear_LS_triangulation_c)
        C[:, 2] = u_normalized[:, i]
        C1 = np.array(linear_LS_triangulation_c)
        C1[:, 2] = u1_normalized[:, i]
        
        # Build A matrix
        linear_LS_triangulation_A[0:2, :] = C.dot(P[0:3, 0:3])    # C * R
        linear_LS_triangulation_A[2:4, :] = C1.dot(P1[0:3, 0:3])    # C1 * R1
        
        # Build b vector
        linear_LS_triangulation_b[0:2, :] = C.dot(P[0:3, 3:4])    # C * t
        linear_LS_triangulation_b[2:4, :] = C1.dot(P1[0:3, 3:4])    # C1 * t1
        linear_LS_triangulation_b *= -1
        
        # Solve for x vector
        cv2.solve(linear_LS_triangulation_A, linear_LS_triangulation_b, x[:, i:i+1], cv2.DECOMP_SVD)
    
    return x

def triangl_pose_est_interactive(img_left, img_right, cameraMatrix, distCoeffs, objp, boardSize):
    """
    Triangulation and relative pose estimation will be performed from LEFT to RIGHT image.
    
    Both images have to contain the whole chessboard,
    in order to make a decent estimation of the relative pose based on 'solvePnP'.
    
    Then the user can manually create matches between non-planar objects.
    If the user omits this step, only triangulation of the chessboard corners will be performed,
    and they will be compared to the real 3D points.
    Otherwise the coordinates of the triangulated points of the manually matched points will be printed,
    and a relative pose estimation will be performed (using the essential matrix),
    this pose estimation will be compared with the decent 'solvePnP' estimation.
    
    During manual matching process,
    switching between LEFT and RIGHT image will be done in a zigzag fashion.
    To stop selecting matches, press SPACE.
    """
    
    # Extract chessboard features
    ret_left, corners_left = cvh.extractChessboardFeatures(img_left, boardSize)
    ret_right, corners_right = cvh.extractChessboardFeatures(img_right, boardSize)
    if not ret_left or not ret_right:
        print "Chessboard is not (entirely) in sight, aborting."
        return
    
    # Calculate P matrix of left pose    # TODO: put 'P' calculation in module like 'quaternions'
    P_left = np.eye(4)
    ret, rvec_left, tvec_left = cv2.solvePnP(
            objp, corners_left, cameraMatrix, distCoeffs )
    P_left[0:3, 0:3], jacob = cv2.Rodrigues(rvec_left)
    P_left[0:3, 3:4] = tvec_left
    
    # Calculate P matrix of right pose
    P_right = np.eye(4)
    ret, rvec_right, tvec_right = cv2.solvePnP(
            objp, corners_right, cameraMatrix, distCoeffs )
    P_right[0:3, 0:3], jacob = cv2.Rodrigues(rvec_right)
    P_right[0:3, 3:4] = tvec_right
    
    
    # Calculate relative pose using the essential matrix    (WARNING: image distortion is not compensated (?))
    F, status = cv2.findFundamentalMat(corners_left, corners_right, cv2.FM_RANSAC, 0.006 * np.amax(corners_left), 0.99)    # threshold from [Snavely07 4.1]
    E = (cameraMatrix.T) .dot (F) .dot (cameraMatrix)    # according to "Multiple View Geometry in C.V." by Hartley&Zisserman (9.12)    TODO check reference
    w, u, vt = cv2.SVDecomp(E, flags=cv2.SVD_MODIFY_A)    # Hartley&Zisserman (9.19)    TODO check reference
    W = np.array([[0., -1., 0.],    # Hartley&Zisserman (9.13)    TODO check reference
                  [1.,  0., 0.],
                  [0.,  0., 1.]])
    R = (u) .dot (W) .dot (vt)    # Hartley&Zisserman (9.19)    TODO check reference
    t = u[:, 2:3]
    P = np.eye(4)
    P[0:3, 0:3] = R
    P[0:3, 3:4] = t
    ret, P_inv = cv2.invert(P)
    
    print "Coherent rotation?", (abs(cv2.determinant(R)) - 1 <= 1e-7)
    
    P_left_result = P_inv.dot(P_right)
    P_right_result = P.dot(P_left)
    
    print "P_left"
    print P_left
    print "P_rel"
    print P
    print "P_right"
    print P_right
    
    print "P_left_result"
    print P_left_result
    print "P_right_result"
    print P_right_result
    
    
    # Triangulate ("user can manually create matches between non-planar objects" is omitted for now)
    def print_to_blender(rvec_left, tvec_left, rvec_right, tvec_right,
                         P_left_result, P_right_result,
                         objp_result):
        print "Camera poses:"
        def print_pose(rvec, tvec):
            ax, an = qwts.axis_and_angle_from_rvec(-rvec)
            print "axis, angle = \\\n", list(ax.reshape(-1)), ",", an    # R
            print "pos = \\\n", list(-cv2.Rodrigues(-rvec)[0].dot(tvec).reshape(-1))    # t
        print "Left"
        print_pose(rvec_left, tvec_left)
        print
        print "Left_result"
        rvec_left_result, jacob = cv2.Rodrigues(P_left_result[0:3, 0:3])
        print_pose(rvec_left_result, P_left_result[0:3, 3:4])
        print
        print "Right"
        print_pose(rvec_right, tvec_right)
        print
        print "Right_result"
        rvec_right_result, jacob = cv2.Rodrigues(P_right_result[0:3, 0:3])
        print_pose(rvec_right_result, P_right_result[0:3, 3:4])
        print
        
        print "Points:"
        print "coords = \\\n", map(list, objp_result)
        print
    
    ret, K_inv = cv2.invert(cameraMatrix)
    objp_result = linear_LS_triangulation(
            corners_left.T, P_left, K_inv,
            corners_right.T, P_right, K_inv )
    print_to_blender(rvec_left, tvec_left, rvec_right, tvec_right, P_left_result, P_right_result, objp_result.T)
    print "objp:"
    print objp
    print "objp_result:"
    print objp_result.T
    
    print "Not yet fully implemented."    # TODO: remove


def realtime_pose_estimation(device_id, filename_base_extrinsics, cameraMatrix, distCoeffs, objp, boardSize):
    """
    This interactive demo will track a chessboard in realtime using a webcam,
    and the WORLD axis-system will be drawn on it: [X Y Z] = [red green blue]
    Further on you will see some data in the bottom-right corner,
    this indicates both the pose of the current image w.r.t. the WORLD axis-system,
    as well as the pose of the current image w.r.t. the previous keyframe pose.
    
    To create a new keyframe while running, press SPACE.
    Each time a new keyframe is generated,
    the corresponding image and data (in txt-format) is written to the 'filename_base_extrinsics' folder.
    
    All poses are defined in the WORLD axis-system,
    the rotation notation follows axis-angle representation: '<unit vector> * <magnitude (degrees)>'.
    
    To quit, press ESC.
    """
    cv2.namedWindow("Image (with axis-system)")
    axis_system_objp = np.array([ [0., 0., 0.],   # Origin (black)
                                  [4., 0., 0.],   # X-axis (red)
                                  [0., 4., 0.],   # Y-axis (green)
                                  [0., 0., 4.] ]) # Z-axis (blue)
    fontFace = cv2.FONT_HERSHEY_DUPLEX
    fontScale = 0.5
    mlt = cvh.MultilineText()
    cap = cv2.VideoCapture(device_id)

    imageNr = 0    # keyframe image id
    rvec_prev = np.zeros((3, 1))
    rvec = None
    tvec_prev = np.zeros((3, 1))
    tvec = None

    # Loop until 'q' or ESC pressed
    last_key_pressed = 0
    while not last_key_pressed in (ord('q'), 27):
        ret_, img = cap.read()
        ret, corners = cvh.extractChessboardFeatures(img, boardSize)

        # If valid features found, solve for 'rvec' and 'tvec'
        if ret == True:
            ret, rvec, tvec = cv2.solvePnP(    # TODO: use Ransac version for other types of features
                    objp, corners, cameraMatrix, distCoeffs )

            # Project axis-system
            imgp_reproj, jacob = cv2.projectPoints(
                    axis_system_objp, rvec, tvec, cameraMatrix, distCoeffs )
            rounding = np.vectorize(lambda x: int(round(x)))
            origin, xAxis, yAxis, zAxis = rounding(imgp_reproj.reshape(-1, 2)) # round to nearest int
            
            # OpenCV's 'rvec' and 'tvec' seem to be defined as follows:
            #   'rvec': rotation transformation: "CAMERA axis-system -> WORLD axis-system"
            #   'tvec': translation of "CAMERA -> WORLD", defined in the "CAMERA axis-system"
            rvec *= -1    # convert to: "WORLD axis-system -> CAMERA axis-system"
            tvec = cv2.Rodrigues(rvec)[0].dot(tvec)    # bring to "WORLD axis-system", ...
            tvec *= -1    # ... and change direction to "WORLD -> CAMERA"
            
            # Calculate pose relative to last keyframe
            rvec_rel = -qwts.delta_rvec(-rvec, -rvec_prev)    # calculate the inverse of the rotation between subsequent "CAMERA -> WORLD" rotations
            tvec_rel = tvec - tvec_prev
            
            # Extract axis and angle, to enhance representation
            rvec_axis, rvec_angle = qwts.axis_and_angle_from_rvec(rvec)
            rvec_rel_axis, rvec_rel_angle = qwts.axis_and_angle_from_rvec(rvec_rel)
            
            # Draw axis-system
            cvh.line(img, origin, xAxis, rgb(255,0,0), thickness=2, lineType=cv2.CV_AA)
            cvh.line(img, origin, yAxis, rgb(0,255,0), thickness=2, lineType=cv2.CV_AA)
            cvh.line(img, origin, zAxis, rgb(0,0,255), thickness=2, lineType=cv2.CV_AA)
            cvh.circle(img, origin, 4, rgb(0,0,0), thickness=-1)    # filled circle, radius 4
            cvh.circle(img, origin, 5, rgb(255,255,255), thickness=2)    # white 'O', radius 5
            
            # Draw pose information
            texts = []
            texts.append("Current pose:")
            texts.append("    Rvec: %s * %.1fdeg" % (format3DVector(rvec_axis), degrees(rvec_angle)))
            texts.append("    Tvec: %s" % format3DVector(tvec))
            texts.append("Relative to previous pose:")
            texts.append("    Rvec: %s * %.1fdeg" % (format3DVector(rvec_rel_axis), degrees(rvec_rel_angle)))
            texts.append("    Tvec: %s" % format3DVector(tvec_rel))
            
            mlt.text(texts[0], fontFace, fontScale*1.5, rgb(150,0,0), thickness=2)
            mlt.text(texts[1], fontFace, fontScale, rgb(255,0,0))
            mlt.text(texts[2], fontFace, fontScale, rgb(255,0,0))
            mlt.text(texts[3], fontFace, fontScale*1.5, rgb(150,0,0), thickness=2)
            mlt.text(texts[4], fontFace, fontScale, rgb(255,0,0))
            mlt.text(texts[5], fontFace, fontScale, rgb(255,0,0))
            mlt.putText(img, (img.shape[1], img.shape[0]))    # put text in bottom-right corner

        # Show Image
        cv2.imshow("Image (with axis-system)", img)
        mlt.clear()
        
        # Save keyframe image when SPACE is pressed
        last_key_pressed = cv2.waitKey(1) & 0xFF
        if last_key_pressed == ord(' ') and ret:
            filename = filename_base_extrinsics + str(imageNr)
            cv2.imwrite(filename + ".jpg", img)    # write image to jpg-file
            textTotal = '\n'.join(texts)
            open(filename + ".txt", 'w').write(textTotal)    # write data to txt-file
            
            print "Saved keyframe image+data to", filename, ":"
            print textTotal
            
            imageNr += 1
            rvec_prev = rvec
            tvec_prev = tvec


        
def get_variable(name, func = lambda x: x):
    value = eval(name)
    value_inp = raw_input("%s [%s]: " % (name, repr(value)))
    if value_inp:
        value = func(value_inp)
        exec("global " + name)
        globals()[name] = value

def main():
    global boardSize, filename_base_chessboards, filename_intrinsics, filename_distorted, filename_triangl_pose_est_left, filename_triangl_pose_est_right, filename_base_extrinsics, device_id
    boardSize = (8, 6)
    filename_base_chessboards = os.path.join("chessboards", "chessboard*.jpg")
    filename_intrinsics = "camera_intrinsics.txt"
    filename_distorted = os.path.join("chessboards", "chessboard07.jpg")    # a randomly chosen image
    filename_triangl_pose_est_left = os.path.join("chessboards", "chessboard07.jpg")    # a randomly chosen image
    filename_triangl_pose_est_right = os.path.join("chessboards", "chessboard08.jpg")    # a randomly chosen image
    filename_base_extrinsics = os.path.join("chessboards_extrinsic", "chessboard")
    device_id = 1    # webcam

    help_text = """\
    Choose between: (in order)
        1: prepare_object_points (required)
        2: calibrate_camera_interactive (required for "reprojection_error")
        3: save_camera_intrinsics
        4: load_camera_intrinsics (required)
        5: undistort_image
        6: reprojection_error
        7: triangl_pose_est_interactive
        8: realtime_pose_estimation (recommended)
        q: quit
    
    Info: Sometimes you will be prompted: 'someVariable [defaultValue]: ',
          in that case you can type a new value,
          or simply press ENTER to preserve the default value.
    """
    from textwrap import dedent
    print dedent(help_text)
    
    inp = ""
    while inp.lower() != "q":
        inp = raw_input("\n: ").strip()
        
        if inp == "1":
            get_variable("boardSize", lambda x: eval("(%s)" % x))
            print    # add new-line
            
            objp = prepare_object_points(boardSize)
        
        elif inp == "2":
            get_variable("filename_base_chessboards")
            from glob import glob
            images = sorted(glob(filename_base_chessboards))
            print    # add new-line
            
            reproj_error, cameraMatrix, distCoeffs, rvecs, tvecs, objectPoints, imagePoints, imageSize = \
                    calibrate_camera_interactive(images, objp, boardSize)
            print "cameraMatrix:\n", cameraMatrix
            print "distCoeffs:\n", distCoeffs
            print "reproj_error:", reproj_error
            
            cv2.destroyAllWindows()
        
        elif inp == "3":
            get_variable("filename_intrinsics")
            print    # add new-line
            
            save_camera_intrinsics(filename_intrinsics, cameraMatrix, distCoeffs, imageSize)
        
        elif inp == "4":
            get_variable("filename_intrinsics")
            print    # add new-line
            
            cameraMatrix, distCoeffs, imageSize = \
                    load_camera_intrinsics(filename_intrinsics)
        
        elif inp == "5":
            get_variable("filename_distorted")
            img = cv2.imread(filename_distorted)
            print    # add new-line
            
            img_undistorted, roi = \
                    undistort_image(img, cameraMatrix, distCoeffs, imageSize)
            cv2.imshow("Original Image", img)
            cv2.imshow("Undistorted Image", img_undistorted)
            print "Press any key to continue."
            cv2.waitKey()
            
            cv2.destroyAllWindows()
        
        elif inp == "6":
            mean_error, square_error = \
                    reprojection_error(cameraMatrix, distCoeffs, rvecs, tvecs, objectPoints, imagePoints, boardSize)
            print "mean absolute error:", mean_error
            print "square error:", square_error
        
        elif inp == "7":
            print triangl_pose_est_interactive.__doc__
            
            get_variable("filename_triangl_pose_est_left")
            img_left = cv2.imread(filename_triangl_pose_est_left)
            get_variable("filename_triangl_pose_est_right")
            img_right = cv2.imread(filename_triangl_pose_est_right)
            print    # add new-line
            
            triangl_pose_est_interactive(img_left, img_right, cameraMatrix, distCoeffs, objp, boardSize)
            
            cv2.destroyAllWindows()
        
        elif inp == "8":
            print realtime_pose_estimation.__doc__
            
            get_variable("device_id", int)
            get_variable("filename_base_extrinsics")
            print    # add new-line
            
            realtime_pose_estimation(device_id, filename_base_extrinsics, cameraMatrix, distCoeffs, objp, boardSize)
            
            cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
