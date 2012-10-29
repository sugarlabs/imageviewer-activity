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
from gi.repository import GObject

import sys
import logging
import cairo
import random
import time
import math

ZOOM_IN_OUT = 0.1


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

        self.surface = None
        self.zoom = None
        self.parent = None
        self.file_location = None
        self._optimal_zoom_flag = True

        self.connect('draw', self.__draw_cb)

        self.angle = 0
        self._zoom_ori = 1.0
        self._angle_ori = 0.0
        self._fast = True
        self._redraw_id = None
        self._switched = False

        # zoom with fixed point
        self._is_touching = False
        self._touch_center = False
        self._old_zoom = None
        self._xofs = 0
        self._yofs = 0

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

    def __draw_cb(self, widget, ctx):
        timeini = time.time()
        logging.error('ImageViewer.draw start')

        if self.surface is None:
            if self.file_location is None:
                return
            logging.error('init surface with image')
            # http://cairographics.org/gdkpixbufpycairo/
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.file_location)
            self.surface = ctx.get_target().create_similar(
                    cairo.CONTENT_COLOR_ALPHA, pixbuf.get_width(),
                    pixbuf.get_height())
            ctx_surface = cairo.Context(self.surface)
            self._pixbuf_to_context(pixbuf, ctx_surface)

        if self.zoom is None:
            self.zoom = self._calc_optimal_zoom()

        w = int(self.surface.get_width() * self.zoom)
        h = int(self.surface.get_height() * self.zoom)
        logging.error('W: %s, H: %s', w, h)

        if self._fast:
            ctx.set_antialias(cairo.ANTIALIAS_NONE)

        scrolled_window = self.get_parent()
        rect = scrolled_window.get_allocation()
        x = y = 0
        if self.angle != 0:
            logging.error('Rotating: %s', self.angle)
            ctx.rotate(self.angle)

            if self.angle == math.pi:
                ctx.translate(-w, -h)

                if rect.width > w:
                    x = -(rect.width - w) / 2
                if rect.height > h:
                    y = -(rect.height - h) / 2

            elif self.angle == math.pi / 2:
                ctx.translate(0, -h)

                # center the image
                if rect.height > w:
                    x = (rect.height - w) / 2
                if rect.width > h:
                    y = -(rect.width - h) / 2

            elif self.angle == math.pi * 3 / 2:
                ctx.translate(-w, 0)

                if rect.height > w:
                    x = -(rect.height - w) / 2
                if rect.width > h:
                    y = (rect.width - h) / 2

        else:
            if rect.width > w:
                x = int((rect.width - w) / 2)
            if rect.height > h:
                y = int((rect.height - h) / 2)
        ctx.translate(x, y)

        if self.zoom != 1:
            logging.error('Scaling: %s', self.zoom)
            ctx.scale(self.zoom, self.zoom)

        ctx.set_source_surface(self.surface, 0, 0)
        if self._fast:
            ctx.get_source().set_filter(cairo.FILTER_NEAREST)
        ctx.paint()
        logging.error('ImageViewer.draw end %f', (time.time() - timeini))

        if not self._fast:
            if self._redraw_id is not None:
                GObject.source_remove(self._redraw_id)
            self._redraw_id = GObject.timeout_add(200,
                    self._redraw_high_quality)

        self._is_touching = False

    def _redraw_high_quality(self):
        self._fast = False
        self._redraw_id = None
        self._redraw()
        return False

    def _redraw(self):
        # README: this is a hack to not raise the 'draw' event (again)
        # when we request more space to show the scroll bars
        w = int(self.surface.get_width() * self.zoom)
        h = int(self.surface.get_height() * self.zoom)

        self._switched = False
        if (self.angle / (math.pi / 2)) % 2 == 1:
            # change image dimensions if it's rotated
            w, h = h, w
            self._switched = True

        self.set_size_request(w, h)
        self._scroll_image()

    def _scroll_image(self):
        # based on Eye Of GNOME code

        w = int(self.surface.get_width() * self.zoom)
        h = int(self.surface.get_height() * self.zoom)

        old_width = int(self.surface.get_width() * self._old_zoom)
        old_height = int(self.surface.get_height() * self._old_zoom)

        scrolled_window = self.get_parent()
        rect = scrolled_window.get_allocation()

        if self._switched:
            # TODO: zoom with fixed point does not work properly when
            # the image is rotated
            return

        if self._is_touching:
            zoom_x_anchor = self._touch_center[1] / rect.width
            zoom_y_anchor = self._touch_center[2] / rect.height
        else:
            zoom_x_anchor = 0.5
            zoom_y_anchor = 0.5

        vadjustment = scrolled_window.get_vadjustment()
        step_inc = vadjustment.get_step_increment()
        page_inc = vadjustment.get_page_increment()

        if old_height < rect.height:
            cy = zoom_y_anchor * old_height / self._old_zoom
        else:
            cy = (self._yofs + zoom_y_anchor * rect.height) / self._old_zoom

        if h < rect.height:
            self._yofs = 0
        else:
            self._yofs = math.floor(cy * self.zoom - \
                    zoom_y_anchor * rect.height + 0.5)

        vadj = max(0, min(self._yofs, h - rect.height))
        vadjustment.configure(vadj, 0, h, step_inc, page_inc,
                              rect.height)

        hadjustment = scrolled_window.get_hadjustment()
        step_inc = hadjustment.get_step_increment()
        page_inc = hadjustment.get_page_increment()

        if old_width < rect.width:
            cx = zoom_x_anchor * old_width / self._old_zoom
        else:
            cx = (self._xofs + zoom_x_anchor * rect.width) / self._old_zoom

        if w < rect.width:
            self._xofs = 0
        else:
            self._xofs = math.floor(cx * self.zoom - \
                    zoom_x_anchor * rect.width + 0.5)

        hadj = max(0, min(self._xofs, w - rect.width))
        hadjustment.configure(hadj, 0, w, step_inc, page_inc,
                              rect.width)

    def set_zoom(self, zoom):
        self._optimal_zoom_flag = False
        self._set_zoom(zoom)

    def set_zoom_relative(self, scale):
        if scale == 1.0:
            self._zoom_ori = self.zoom
        self._set_zoom(self._zoom_ori * scale)

    def set_angle_relative(self, diff):
        if diff == 0.0:
            self._angle_ori = self.angle
        self.set_angle(self._angle_ori + diff)

    def set_angle(self, angle):
        self._optimal_zoom_flag = True

        self.angle = angle % (2 * math.pi)
        self._redraw()
        self.emit('angle-changed')

    def zoom_in(self):
        self.set_zoom(self.zoom + ZOOM_IN_OUT)
        # TODO: this value is not valid
        if self.zoom > (4):
            return False
        else:
            return True

    def zoom_out(self):
        self.set_zoom(self.zoom - ZOOM_IN_OUT)
        # TODO: this value is not valid
        if self.zoom <= 0.2:
            return False
        else:
            return True

    def _pixbuf_to_context(self, pixbuf, context, x=0, y=0):
        # copy from the pixbuf to the drawing context
        context.save()
        context.translate(x, y)
        Gdk.cairo_set_source_pixbuf(context, pixbuf, 0, 0)
        context.paint()
        context.restore()

    def set_file_location(self, file_location):
        logging.debug('Loading image from: %s', file_location)

        self.file_location = file_location
        self.zoom = None
        self.queue_draw()

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

        surface_width = self.surface.get_width()
        surface_height = self.surface.get_height()

        if self._switched:
            surface_width, surface_height = \
                surface_height, surface_width

        if width < surface_width or \
                height < surface_height:
            # Image is larger than allocated size
            zoom = min(width / surface_width,
                    height / surface_height)
        else:
            zoom = 1

        logging.debug('Optimal zoom: %s', zoom)
        return zoom

    def _set_zoom(self, zoom):
        self._old_zoom = self.zoom
        self.zoom = zoom
        self._redraw()
        self.emit('zoom-changed')


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
