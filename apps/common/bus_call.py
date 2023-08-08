################################################################################
# SPDX-FileCopyrightText: Copyright (c) 2019-2021 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import gi
import sys
gi.require_version('Gst', '1.0')
from gi.repository import Gst
def bus_call(bus, message, loop):
    t = message.type
    if t == Gst.MessageType.EOS:
        sys.stdout.write("End-of-stream\n")
        loop.quit()
    elif t==Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        sys.stderr.write("Warning: %s: %s\n" % (err, debug))
    elif t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        sys.stderr.write("Error: %s: %s\n" % (err, debug))
        loop.quit()
    return True

# def bus_call(bus, message, loop):
#     if message.type == Gst.MessageType.EOS:
#         sys.stdout.write("End-of-stream\n")
#         loop.quit()
#     elif message.type == Gst.MessageType.ERROR:
#         err, debug = message.parse_error()
#         out_str = " Error: %s: %s\n" % (err, debug)

#         sys.stdout.write(out_str)
#         loop.quit()
#     elif message.type == Gst.MessageType.STATE_CHANGED:
#         old, new, pending = message.parse_state_changed()
#         out_str = 'State changed from %s to %s (pending=%s)\n' % (old.value_name, new.value_name, pending.value_name)
#         sys.stdout.write(out_str)
#     elif message.type == Gst.MessageType.STREAM_STATUS:
#         type_, owner = message.parse_stream_status()
#         out_str = 'Stream status changed to %s (owner=%s)\n' % (type_.value_name, owner.name)
#         sys.stdout.write(out_str)
#     elif message.type == Gst.MessageType.DURATION_CHANGED:
#         sys.stdout.write('Duration changed\n')
#     else:
#         out_str = '!! Unknown message type: %r \n' % message.type
#         sys.stdout.write(out_str)
#     return True