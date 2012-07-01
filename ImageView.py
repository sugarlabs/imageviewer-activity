# Copyright (C) 2008, One Laptop per Child
# Author: Sayamindu Dasgupta <sayamindu@laptop.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

from __future__ import division

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import cairo
from gi.repository import GObject

import sys
import logging

import random


class ImageViewer(Gtk.DrawingArea):
    __gsignals__ = {
        #'expose-event': (
        #    'override'),
        'zoom-changed': (
            GObject.SignalFlags.RUN_FIRST, None, []),
        'angle-changed': (
            GObject.SignalFlags.RUN_FIRST, None, []),
        }

    __gproperties__ = {
        'zoom': (
            GObject.TYPE_FLOAT, 'Zoom Factor', 'Factor of zoom',
            0, 4, 1, GObject.PARAM_READWRITE),
        'angle': (
            GObject.TYPE_INT, 'Angle', 'Angle of rotation',
            0, 360, 0, GObject.PARAM_READWRITE),
        'file_location': (
            GObject.TYPE_STRING, 'File Location', 'Location of the image file',
            '', GObject.PARAM_READWRITE),
        }

    def __init__(self):
        GObject.GObject.__init__(self)
        self.set_app_paintable(True)

        self.pixbuf = None
        self.zoom = None
        self.parent = None
        self.file_location = None
        self._temp_pixbuf = None
        self._image_changed_flag = True
        self._optimal_zoom_flag = True

        self.connect('draw', self.draw)

        self.angle = 0

    def do_get_property(self, pspec):
        if pspec.name == 'zoom':
            return self.zoom
        elif pspec.name == 'angle':
            return self.angle
        elif pspec.name == 'file_location':
            return self.file_location
        else:
            raise AttributeError('unknown property %s' % pspec.name)

    def do_set_property(self, pspec, value):
        if pspec.name == 'zoom':
            self.set_zoom(value)
        elif pspec.name == 'angle':
            self.set_angle(value)
        elif pspec.name == 'file_location':
            self.set_file_location(value)
        else:
            raise AttributeError('unknown property %s' % pspec.name)

    def set_optimal_zoom(self):
        self._optimal_zoom_flag = True
        self._set_zoom(self._calc_optimal_zoom())

    def update_optimal_zoom(self):
        if self._optimal_zoom_flag:
            self._set_zoom(self._calc_optimal_zoom())

    def draw(self, widget, ctx):
        if not self.pixbuf:
            return
        if self.zoom is None:
            self.zoom = self._calc_optimal_zoom()

        if self._temp_pixbuf is None or self._image_changed_flag:
            self._temp_pixbuf = self._convert_pixbuf(self.pixbuf)
            self._image_changed_flag = False

        rect = self.get_allocation()
        x = rect.x
        y = rect.y

        width = self._temp_pixbuf.get_width()
        height = self._temp_pixbuf.get_height()

        if self.parent:
            rect = self.parent.get_allocation()
            if rect.width > width:
                x = int(((rect.width - x) - width) / 2)

            if rect.height > height:
                y = int(((rect.height - y) - height) / 2)

        self.set_size_request(self._temp_pixbuf.get_width(),
                self._temp_pixbuf.get_height())

        Gdk.cairo_set_source_pixbuf(ctx, self._temp_pixbuf, x, y)

        ctx.paint()

    def set_zoom(self, zoom):
        self._optimal_zoom_flag = False
        self._set_zoom(zoom)

    def set_angle(self, angle):
        self._image_changed_flag = True
        self._optimal_zoom_flag = True

        self.angle = angle

        if self.props.window:
            alloc = self.get_allocation()
            rect = cairo.RectangleInt()
            rect.x = alloc.x
            rect.y = alloc.y
            rect.width = alloc.width
            rect.height = alloc.height
            self.props.window.invalidate_rect(rect, True)
            self.props.window.process_updates(True)

        self.emit('angle-changed')

    def zoom_in(self):
        self.set_zoom(self.zoom + 0.2)
        if self.zoom > (4):
            return False
        else:
            return True

    def zoom_out(self):
        self.set_zoom(self.zoom - 0.2)
        if self.zoom <= 0.2:
            return False
        else:
            return True

    def set_file_location(self, file_location):
        self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_location)
        self.file_location = file_location
        self.zoom = None
        self._image_changed_flag = True

        if self.props.window:
            alloc = self.get_allocation()
            rect = cairo.RectangleInt()
            rect.x = alloc.x
            rect.y = alloc.y
            rect.width = alloc.width
            rect.height = alloc.height
            self.props.window.invalidate_rect(rect, True)
            self.props.window.process_updates(True)

    def _calc_optimal_zoom(self):
        # This tries to figure out a best fit model
        # If the image can fit in, we show it in 1:1,
        # in any other case we show it in a fit to screen way

        if isinstance(self.parent, Gtk.Viewport):
            rect = self.parent.parent.get_allocation()
        else:
            rect = self.parent.get_allocation()
        width = rect.width
        height = rect.height

        pixbuf = self.pixbuf
        if width < pixbuf.get_width() or height < pixbuf.get_height():
            # Image is larger than allocated size
            zoom = min(width / pixbuf.get_width(),
                    height / pixbuf.get_height())
        else:
            zoom = 1

        return zoom

    def _set_zoom(self, zoom):
        self._image_changed_flag = True
        self.zoom = zoom

        if self.props.window:
            alloc = self.get_allocation()
            rect = cairo.RectangleInt()
            rect.x = alloc.x
            rect.y = alloc.y
            rect.width = alloc.width
            rect.height = alloc.height
            self.props.window.invalidate_rect(rect, True)
            self.props.window.process_updates(True)

        self.emit('zoom-changed')

    def _convert_pixbuf(self, pixbuf):
        if self.angle == 0:
            rotate = GdkPixbuf.PixbufRotation.NONE
        elif self.angle == 90:
            rotate = GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE
        elif self.angle == 180:
            rotate = GdkPixbuf.PixbufRotation.UPSIDEDOWN
        elif self.angle == 270:
            rotate = GdkPixbuf.PixbufRotation.CLOCKWISE
        elif self.angle == 360:
            self.angle = 0
            rotate = GdkPixbuf.PixbufRotation.NONE
        else:
            logging.warning('Got unsupported rotate angle')

        if rotate != GdkPixbuf.PixbufRotation.NONE:
            pixbuf = pixbuf.rotate_simple(rotate)

        if self.zoom != 1:
            width = int(pixbuf.get_width() * self.zoom)
            height = int(pixbuf.get_height() * self.zoom)
            pixbuf = pixbuf.scale_simple(width, height,
                                         GdkPixbuf.InterpType.TILES)

        return pixbuf


def update(view_object):
    #return view_object.zoom_out()
    angle = 90 * random.randint(0, 4)
    view_object.set_angle(angle)

    return True


if __name__ == '__main__':
    window = Gtk.Window()

    vadj = Gtk.Adjustment()
    hadj = Gtk.Adjustment()
    sw = Gtk.ScrolledWindow(hadj, vadj)

    view = ImageViewer()

    view.set_file_location(sys.argv[1])


    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)


    sw.add_with_viewport(view)
    window.add(sw)

    window.set_size_request(800, 600)

    window.show_all()

    GObject.timeout_add(1000, update, view)

    Gtk.main()
