#!/usr/bin/env python3

################################################################################
# SPDX-FileCopyrightText: Copyright (c) 2020-2021 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
################################################################################

import os
import argparse
import sys
sys.path.append('../')

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import GLib, Gst, GstRtspServer
from common.is_aarch_64 import is_aarch64
from common.bus_call import bus_call

import pyds


PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3
URI_CSI = "argus://"
URI_USB = "/dev/video"


def osd_sink_pad_buffer_probe(pad,info,u_data):
    frame_number=0
    #Intiallizing object counter with 0.
    obj_counter = {
        PGIE_CLASS_ID_VEHICLE:0,
        PGIE_CLASS_ID_PERSON:0,
        PGIE_CLASS_ID_BICYCLE:0,
        PGIE_CLASS_ID_ROADSIGN:0
    }
    num_rects=0

    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return

    # Retrieve batch metadata from the gst_buffer
    # Note that pyds.gst_buffer_get_nvds_batch_meta() expects the
    # C address of gst_buffer as input, which is obtained with hash(gst_buffer)
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            # Note that l_frame.data needs a cast to pyds.NvDsFrameMeta
            # The casting is done by pyds.NvDsFrameMeta.cast()
            # The casting also keeps ownership of the underlying memory
            # in the C code, so the Python garbage collector will leave
            # it alone.
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        frame_number=frame_meta.frame_num
        num_rects = frame_meta.num_obj_meta
        l_obj=frame_meta.obj_meta_list
        while l_obj is not None:
            try:
                # Casting l_obj.data to pyds.NvDsObjectMeta
                obj_meta=pyds.NvDsObjectMeta.cast(l_obj.data)
            except StopIteration:
                break
            obj_counter[obj_meta.class_id] += 1
            try: 
                l_obj=l_obj.next
            except StopIteration:
                break

        # Acquiring a display meta object. The memory ownership remains in
        # the C code so downstream plugins can still access it. Otherwise
        # the garbage collector will claim it when this probe function exits.
        display_meta=pyds.nvds_acquire_display_meta_from_pool(batch_meta)
        display_meta.num_labels = 1
        py_nvosd_text_params = display_meta.text_params[0]
        # Setting display text to be shown on screen
        # Note that the pyds module allocates a buffer for the string, and the
        # memory will not be claimed by the garbage collector.
        # Reading the display_text field here will return the C address of the
        # allocated string. Use pyds.get_string() to get the string content.
        py_nvosd_text_params.display_text = "Frame Number={} Number of Objects={} Vehicle_count={} Person_count={}".format(frame_number, num_rects, obj_counter[PGIE_CLASS_ID_VEHICLE], obj_counter[PGIE_CLASS_ID_PERSON])

        # Now set the offsets where the string should appear
        py_nvosd_text_params.x_offset = 10
        py_nvosd_text_params.y_offset = 12

        # Font , font-color and font-size
        py_nvosd_text_params.font_params.font_name = "Serif"
        py_nvosd_text_params.font_params.font_size = 10
        # set(red, green, blue, alpha); set to White
        py_nvosd_text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)

        # Text background color
        py_nvosd_text_params.set_bg_clr = 1
        # set(red, green, blue, alpha); set to Black
        py_nvosd_text_params.text_bg_clr.set(0.0, 0.0, 0.0, 1.0)
        # Using pyds.get_string() to get display_text as string
        print(pyds.get_string(py_nvosd_text_params.display_text))
        pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)
        try:
            l_frame=l_frame.next
        except StopIteration:
            break
			
    return Gst.PadProbeReturn.OK	


# source = make_elm_or_print_err(
#     "nvarguscamerasrc", "nv-argus-camera-source", "RaspiCam input"
# )
# source.set_property("sensor-id", int(input_device))
# source.set_property("bufapi-version", 1)
def make_encoder(codec, bitrate):
    if codec == "X264":
        print("Creating x264enc")
        encoder = Gst.ElementFactory.make("x264enc", "encoder_x264")
        if not encoder:
            sys.stderr.write(" Unable to create encoder x264 \n")
        encoder.set_property("speed-preset", 1) # 1 is superfast, 2 is veryfast, 3 is faster, 4 is fast, 5 is medium, 6 is slow, 7 is slower, 8 is veryslow, 9 is placebo
        encoder.set_property("tune", "zerolatency")
        encoder.set_property("bitrate", bitrate // 1000)

    elif codec == "H264":
        print("Creating nvidia hardware H264 encoder")
        encoder = Gst.ElementFactory.make("nvv4l2h264enc", "encoder_h264")
        if not encoder:
            sys.stderr.write(" Unable to create encoder H264 \n")
        encoder.set_property("bitrate", bitrate)
        if is_aarch64():
            encoder.set_property('preset-level', 1)
            encoder.set_property('insert-sps-pps', 1)
    
    elif codec == "H265":
        print("Creating nvidia hardware H265 encoder")
        encoder = Gst.ElementFactory.make("nvv4l2h265enc", "encoder")
        if not encoder:
            sys.stderr.write(" Unable to create encoder H265 \n")
        encoder.set_property("bitrate", bitrate)
        if is_aarch64():
            encoder.set_property('preset-level', 1)
            encoder.set_property('insert-sps-pps', 1)

    return encoder



class IPv4Action(argparse.Action):

    def __call__(self, parser, namespace, values, option_string=None):
        ip = values.split('.')

        if len(ip) != 4:
            raise argparse.ArgumentError("{} is an invalid IPv4 address".format(values))
        
        for octet in ip:
            if not (0 <= int(octet) and int(octet) <= 255):
                raise argparse.ArgumentError("{} is an invalid IPv4 address".format(values))
        
        setattr(namespace, self.dest, values)

class UDPPortAction(argparse.Action):

    def __call__(self, parser, namespace, values, option_string=None):
        if not (5000 <= int(values) and int(values) <= 65535):
            raise argparse.ArgumentError("{} is an invalid UDP port number must be between 5000 and 65535".format(values))
        
        setattr(namespace, self.dest, values)



def main(args):

    codec = args.codec
    bitrate = args.bitrate
    stream_path = args.input
    host = args.host
    udp_sink_port_num = args.port
    fps = args.framerate
    height = args.height
    width = args.width
    is_streammux = args.streammux
    debug_level = args.debug

    # Standard GStreamer initialization
    Gst.init(None)
    if debug_level > 0:
        # For debugging must be after Gst.init
        Gst.debug_set_active(True)
        Gst.debug_set_default_threshold(debug_level)
        # no colored text in output logs
        if args.colordebug == 0:
            Gst.debug_set_color_mode(0)



    # Create gstreamer elements
    # Create Pipeline element that will form a connection of other elements
    print("Creating Pipeline \n ")
    pipeline = Gst.Pipeline()
    if not pipeline:
        sys.stderr.write(" Unable to create Pipeline \n")
    
    # Create Elements 
    print("Creating Elements: .... \n")
    # Source element for reading from the camera
    print("Creating Source")
    source = Gst.ElementFactory.make("nvarguscamerasrc", "nv-argus-camera-source")
    if not source:
        sys.stderr.write(" Unable to create Source \n")
    sensor_id = int(stream_path[len(URI_CSI):])
    source.set_property("sensor-id", sensor_id)
    try:
        source.set_property("bufapi-version", 1)
    except Exception:
        pass


    # Caps for the source pad of the source element
    caps_nvarguscamerasrc = Gst.ElementFactory.make("capsfilter", "nvmm_caps")
    if not caps_nvarguscamerasrc:
        sys.stderr.write(" Unable to create capsfilter \n")
    camera_props = "video/x-raw(memory:NVMM), width=(int){}, height=(int){}, framerate=(fraction){}/1, format=(string)NV12".format(width, height, fps)
    caps_nvarguscamerasrc.set_property("caps", Gst.Caps.from_string(camera_props))



    print("Creating Video Converter \n")
    # Adding videoconvert -> nvvideoconvert as not all
    # raw formats are supported by nvvideoconvert;
    # Say YUYV is unsupported - which is the common
    # raw format for many logi usb cams
    # In case we have a camera with raw format supported in
    # nvvideoconvert, GStreamer plugins' capability negotiation
    # shall be intelligent enough to reduce compute by
    # videoconvert doing passthrough (TODO we need to confirm this)

    # videoconvert to make sure a superset of raw formats are supported
    vidconvsrc = Gst.ElementFactory.make("videoconvert", "convertor_src1")
    if not vidconvsrc:
        sys.stderr.write(" Unable to create videoconvert \n")

    # nvvideoconvert to convert incoming raw buffers to NVMM Mem (NvBufSurface API)
    nvvidconvsrc = Gst.ElementFactory.make("nvvideoconvert", "convertor_src2")
    if not nvvidconvsrc:
        sys.stderr.write(" Unable to create Nvvideoconvert \n")

    # Create nvstreammux instance to form batches from one or more sources.
    print("Creating Streammux \n ")
    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux:
        sys.stderr.write(" Unable to create NvStreamMux \n")

    # Use nvinfer to run inferencing on camera's stream.
    print("Creating pgie \n ")
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    if not pgie:
        sys.stderr.write(" Unable to create pgie \n")

    # Convert from NV12 to RGBA as required by nvosd
    print("Creating nvvidconv \n")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")
    if not nvvidconv:
        sys.stderr.write(" Unable to create nvvidconv \n")

    # Create OSD to draw on the converted RGBA buffer
    print("Creating nvosd \n ")
    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
    if not nvosd:
        sys.stderr.write(" Unable to create nvosd \n")
    nvvidconv_postosd = Gst.ElementFactory.make("nvvideoconvert", "convertor_postosd")
    if not nvvidconv_postosd:
        sys.stderr.write(" Unable to create nvvidconv_postosd \n")
    
    # Create a caps filter
    caps_vidconvsrc = Gst.ElementFactory.make("capsfilter", "filter")
    caps_vidconvsrc.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM)"))
    
    caps = None
    if codec == "H264" or codec == "H265":
        caps = Gst.ElementFactory.make("capsfilter", "filter_enc")
        caps.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=I420"))
    else:
        caps = Gst.ElementFactory.make("capsfilter", "filter_enc")
        caps.set_property("caps", Gst.Caps.from_string("video/x-raw, format=I420"))
    
    # Make the encoder 
    encoder = make_encoder(codec, bitrate)


    queue = Gst.ElementFactory.make("queue", "queue")
    if not queue:
        sys.stderr.write(" Unable to create queue \n")
    
    # Make the payload-encode video into RTP packets
    rtppay = Gst.ElementFactory.make("rtph264pay", "rtppay")
    if codec == "X264" or codec == "H264":
        rtppay = Gst.ElementFactory.make("rtph264pay", "rtppay")
        print("Creating rtph264pay \n ")
    elif codec == "H265":
        rtppay = Gst.ElementFactory.make("rtph265pay", "rtppay")
        print("Creating rtph265pay \n ")
    
    if not rtppay:
        sys.stderr.write(" Unable to create rtppay \n")

    # Make the UDP sink
    udp_sink = Gst.ElementFactory.make("udpsink", "udpsink")
    if not udp_sink:
        sys.stderr.write(" Unable to create udpsink \n")

    # Set udp_sink properties
    udp_sink.set_property("host", host)
    udp_sink.set_property("port", udp_sink_port_num)
    udp_sink.set_property("async", False)
    udp_sink.set_property("sync", 1)

    print("Playing cam %s " %stream_path)
    streammux.set_property('width', width)
    streammux.set_property('height', height)
    streammux.set_property('batch-size', 1)
    streammux.set_property('batched-push-timeout', 4000000)

    pgie.set_property('config-file-path', "dstest1_pgie_config.txt")

    print("Adding elements to Pipeline \n")
    pipeline.add(source)
    pipeline.add(caps_nvarguscamerasrc)
    pipeline.add(vidconvsrc)
    pipeline.add(nvvidconvsrc)
    pipeline.add(caps_vidconvsrc)
    pipeline.add(streammux)
    pipeline.add(pgie)
    pipeline.add(nvvidconv)
    pipeline.add(nvosd)
    pipeline.add(nvvidconv_postosd)
    pipeline.add(caps)
    pipeline.add(encoder)
    pipeline.add(queue)
    pipeline.add(rtppay)
    pipeline.add(udp_sink)

    # Link the elements together:
    print("Linking elements in the Pipeline \n")
    source.link(caps_nvarguscamerasrc)
    caps_nvarguscamerasrc.link(vidconvsrc)
    vidconvsrc.link(nvvidconvsrc)
    if is_streammux == 1:
        nvvidconvsrc.link(caps_vidconvsrc)
        sinkpad = streammux.get_request_pad("sink_0")
        if not sinkpad:
            sys.stderr.write(" Unable to get the sink pad of streammux \n")
        srcpad = caps_vidconvsrc.get_static_pad("src")
        if not srcpad:
            sys.stderr.write(" Unable to get source pad of caps_vidconvsrc \n")
        srcpad.link(sinkpad)
        streammux.link(pgie)
        pgie.link(nvvidconv)
        nvvidconv.link(nvosd)
        nvosd.link(nvvidconv_postosd)
        nvvidconv_postosd.link(caps)
        caps.link(encoder)
        
    else:
        nvvidconvsrc.link(encoder)
    
    encoder.link(queue)
    queue.link(rtppay)
    rtppay.link(udp_sink)




    # create an event loop and feed gstreamer bus mesages to it
    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", bus_call, loop)

    # Start streaming
    rtsp_port_num = udp_sink_port_num + 5
    server = GstRtspServer.RTSPServer.new()
    server.props.service = "%d" % rtsp_port_num
    server.attach(None)

    factory = GstRtspServer.RTSPMediaFactory.new()
    factory.set_launch( "( udpsrc name=pay0 port=%d buffer-size=524288 caps=\"application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)%s, payload=96 \" )" % (udp_sink_port_num, codec))
    factory.set_shared(True)
    server.get_mount_points().add_factory("/ds-test", factory)
    print("\n *** DeepStream: Launched RTSP Streaming at rtsp://{}:{}/ds-test ***\n\n".format(host, rtsp_port_num))

    # Lets add probe to get informed of the meta data generated, we add probe to
    # the sink pad of the osd element, since by that time, the buffer would have
    # had got all the metadata.
    osdsinkpad = nvosd.get_static_pad("sink")
    if not osdsinkpad:
        sys.stderr.write(" Unable to get sink pad of nvosd \n")
    
    osdsinkpad.add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0)





    # start play back and listen to events
    print("Starting pipeline \n")
    pipeline.set_state(Gst.State.PLAYING)
    
    # show graph of pipeline
    if debug_level > 0:
        print("dot file is generated as \"test.dot\" in current directory \n")
        fie = Gst.debug_bin_to_dot_data(pipeline, Gst.DebugGraphDetails.ALL)
        with open("deepstreamtest.dot", "w") as fes:
            fes.write(fie)
        # To convert to png: 
        # dot -Tpng deep_stream_test.dot > deep_stream_test.png

    try:
        loop.run()
    except:
        pass
    # cleanup
    pipeline.set_state(Gst.State.NULL)
    

def parse_args():
    # parser = argparse.ArgumentParser(description='RTSP Output Sample Application Help ')
    # parser.add_argument("-i", "--input",
    #               help="Path to input H264 elementry stream", required=True)
    # parser.add_argument("-c", "--codec", default="X264",
    #               help="RTSP Streaming Codec H264/H265 , default=H264", choices=['H264','H265', 'X264'])
    # parser.add_argument("-b", "--bitrate", default=4000000,
    #               help="Set the encoding bitrate ", type=int)
    # # Check input arguments
    # if len(sys.argv)==1:
    #     parser.print_help(sys.stderr)
    #     sys.exit(1)
    # args = parser.parse_args()

    # codec = args.codec
    # bitrate = args.bitrate
    # stream_path = args.input
    # return 0
    parser = argparse.ArgumentParser(description="CSI to RTSP sample app help ")
    parser.add_argument("-i", "--input", help="Path use", default="argus://0", choices=["argus://0", "/dev/video0"])
    parser.add_argument("-c", "--codec", default="H264", help="RTSP Streaming Codec H264/H265 , default=H264", choices=["H264", "H265", "X264"])
    parser.add_argument("-b", "--bitrate", default=4000000, help="Set the encoding bitrate ", type=int)
    parser.add_argument("-p", "--port", default=5400, action=UDPPortAction, help="Set the UDP port number where 5000 <= port <= 65535 ", type=int)
    parser.add_argument("-hst", "--host", default="127.0.0.1", action=IPv4Action, help="Set the host IPv4 address xxx.xxx.xxx.xxx", type=str)
    parser.add_argument("-fps", "--framerate", default=30, help="Set the framerate", type=int)
    parser.add_argument("-ht", "--height", default=720, help="Set the height", type=int)
    parser.add_argument("-wd", "--width", default=1280, help="Set the width", type=int)
    parser.add_argument("-nvs", "--streammux", default=1, help="If streammux used or not", choices=[0, 1], type=int)
    parser.add_argument("-dbg", "--debug", default=0, help="If debug used or not, default=0 (no debug) [0, 1, 2, 3, 4, 5, 6, 7, 8]", choices=[0, 1, 2, 3, 4, 5, 6, 7], type=int)
    parser.add_argument("-cl", "--colordebug", default=0, help="If color debug used or not, default=0 (no color debug) [0, 1]", choices=[0, 1], type=int)
    args = parser.parse_args()

    # Print current configuration
    for arg in vars(args):
        print(arg, getattr(args, arg))
    
    return args


if __name__ == '__main__':
    # parse_args()
    # sys.exit(main(sys.argv))
    args_use = parse_args()
    main(args_use)


