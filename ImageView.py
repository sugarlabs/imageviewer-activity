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

import logging
import cairo
import math

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import GObject

ZOOM_STEP = 0.05
ZOOM_MAX = 10
ZOOM_MIN = 0.05


def _surface_from_file(file_location, ctx):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_location)
    surface = ctx.get_target().create_similar(
        cairo.CONTENT_COLOR_ALPHA, pixbuf.get_width(),
        pixbuf.get_height())

    ctx_surface = cairo.Context(surface)
    Gdk.cairo_set_source_pixbuf(ctx_surface, pixbuf, 0, 0)
    ctx_surface.paint()
    return surface

def _rotate_surface(surface, direction):
    ctx = cairo.Context(surface)
    new_surface = ctx.get_target().create_similar(
        cairo.CONTENT_COLOR_ALPHA, surface.get_height(),
        surface.get_width())

    ctx_surface = cairo.Context(new_surface)

    if direction == 1:
        ctx_surface.translate(surface.get_height(), 0)
    else:
        ctx_surface.translate(0, surface.get_width())

    ctx_surface.rotate(math.pi / 2 * direction)

    ctx_surface.set_source_surface(surface, 0, 0)
    ctx_surface.paint()

    return new_surface

class ImageViewer(Gtk.DrawingArea, Gtk.Scrollable):
    __gtype_name__ = 'ImageViewer'

    __gproperties__ = {
        "hscroll-policy": (Gtk.ScrollablePolicy, "hscroll-policy",
                           "hscroll-policy", Gtk.ScrollablePolicy.MINIMUM,
                           GObject.PARAM_READWRITE),
        "hadjustment": (Gtk.Adjustment, "hadjustment", "hadjustment",
                        GObject.PARAM_READWRITE),
        "vscroll-policy": (Gtk.ScrollablePolicy, "hscroll-policy",
                           "hscroll-policy", Gtk.ScrollablePolicy.MINIMUM,
                           GObject.PARAM_READWRITE),
        "vadjustment": (Gtk.Adjustment, "hadjustment", "hadjustment",
                        GObject.PARAM_READWRITE),
    }
    def __init__(self):
        Gtk.DrawingArea.__init__(self)

        self._file_location = None
        self._surface = None
        self._zoom = None
        self._target_point = None
        self._anchor_point = None

        self._in_dragtouch = False
        self._in_zoomtouch = False
        self._zoomtouch_scale = 1

        self._in_scrolling = False
        self._scrolling_hid = None
        self._hadj = None
        self._vadj = None
        self._hadj_value_changed_hid = None
        self._vadj_value_changed_hid = None

        self.connect('draw', self.__draw_cb)

    def set_file_location(self, file_location):
        self._file_location = file_location
        self.queue_draw()

    def do_get_property(self, prop):
        pass

    def do_set_property(self, prop, value):
        if prop.name == 'hadjustment':
            if value is not None:
                hadj = value
                self._hadj_value_changed_hid = \
                    hadj.connect('value-changed', self.__hadj_value_changed_cb)
                self._hadj = hadj

        elif prop.name == 'vadjustment':
            if value is not None:
                vadj = value
                self._vadj_value_changed_hid = \
                    vadj.connect('value-changed', self.__vadj_value_changed_cb)
                self._vadj = vadj

    def _update_adjustments(self):
        alloc = self.get_allocation()
        scaled_width = self._surface.get_width() * self._zoom
        scaled_height = self._surface.get_height() * self._zoom

        page_size_x = alloc.width * 1.0 / scaled_width
        self._hadj.set_lower(0)
        self._hadj.set_page_size(page_size_x)
        self._hadj.set_upper(1.0)
        self._hadj.set_step_increment(0.1)
        self._hadj.set_page_increment(0.5)

        page_size_y = alloc.height * 1.0 / scaled_height
        self._vadj.set_lower(0)
        self._vadj.set_page_size(page_size_y)
        self._vadj.set_upper(1.0)
        self._vadj.set_step_increment(0.1)
        self._vadj.set_page_increment(0.5)

        anchor_scaled = (self._anchor_point[0] * self._zoom,
                         self._anchor_point[1] * self._zoom)

        # This vector is the top left coordinate of the scaled image.
        scaled_image_topleft = (self._target_point[0] - anchor_scaled[0],
                                self._target_point[1] - anchor_scaled[1])

        max_topleft = (scaled_width - alloc.width,
                       scaled_height - alloc.height)

        max_value = (1.0 - page_size_x,
                     1.0 - page_size_y)

        # This two linear functions map the topleft corner of the
        # image to the value each adjustment.

        if max_topleft[0] != 0:
            self._hadj.disconnect(self._hadj_value_changed_hid)
            self._hadj.set_value(-1 * max_value[0] *
                                  scaled_image_topleft[0] / max_topleft[0])
            self._hadj_value_changed_hid = \
                self._hadj.connect('value-changed',
                                   self.__hadj_value_changed_cb)

        if max_topleft[1] != 0:
            self._vadj.disconnect(self._vadj_value_changed_hid)
            self._vadj.set_value(-1 * max_value[1] *
                                  scaled_image_topleft[1] / max_topleft[1])
            self._vadj_value_changed_hid = \
                self._vadj.connect('value-changed',
                                   self.__vadj_value_changed_cb)

    def _stop_scrolling(self):
        self._in_scrolling = False
        self.queue_draw()
        return False

    def _start_scrolling(self):
        if not self._in_scrolling:
            self._in_scrolling = True

        # Add or update a timer after which the in_scrolling flag will
        # be set to False.  This is to perform a faster drawing while
        # scrolling.
        if self._scrolling_hid is not None:
            GObject.source_remove(self._scrolling_hid)
        self._scrolling_hid = GObject.timeout_add(200,
                                                  self._stop_scrolling)

    def __hadj_value_changed_cb(self, adj):
        # move anchor and queue draw
        alloc = self.get_allocation()

        dif = 10
        self._anchor_point = (self._anchor_point[0] + dif,
                              self._anchor_point[1])

        self._start_scrolling()
        self.queue_draw()

    def __vadj_value_changed_cb(self, adj):

        dif = 10
        self._anchor_point = (self._anchor_point[0],
                              self._anchor_point[1] + dif)

        self._start_scrolling()
        self.queue_draw()

    def _center_target_point(self):
        alloc = self.get_allocation()
        self._target_point = (alloc.width / 2, alloc.height / 2)

    def _center_anchor_point(self):
        self._anchor_point = (self._surface.get_width() / 2,
                              self._surface.get_height() / 2)

    def _center_if_small(self):
        # If at the current size the image surface is smaller than the
        # available space, center it on the canvas.

        alloc = self.get_allocation()

        scaled_width = self._surface.get_width() * self._zoom
        scaled_height = self._surface.get_height() * self._zoom

        if alloc.width >= scaled_width and alloc.height >= scaled_height:
            self._center_target_point()
            self._center_anchor_point()
            self.queue_draw()

    def set_zoom(self, zoom):
        if zoom < ZOOM_MIN or zoom > ZOOM_MAX:
            return
        self._zoom = zoom
        self.queue_draw()

    def get_zoom(self):
        return self._zoom

    def can_zoom_in(self):
        return self._zoom + ZOOM_STEP < ZOOM_MAX
        self._update_adjustments()

    def can_zoom_out(self):
        return self._zoom - ZOOM_STEP > ZOOM_MIN
        self._update_adjustments()

    def zoom_in(self):
        if not self.can_zoom_in():
            return
        self._zoom += ZOOM_STEP
        self._update_adjustments()
        self.queue_draw()

    def zoom_out(self):
        if not self.can_zoom_out():
            return
        self._zoom -= ZOOM_MIN

        self._center_if_small()
        self._update_adjustments()
        self.queue_draw()

    def zoom_to_fit(self):
        # This tries to figure out a best fit model
        # If the image can fit in, we show it in 1:1,
        # in any other case we show it in a fit to screen way

        alloc = self.get_allocation()

        surface_width = self._surface.get_width()
        surface_height = self._surface.get_height()

        if alloc.width < surface_width or alloc.height < surface_height:
            # Image is larger than allocated size
            self._zoom = min(alloc.width * 1.0 / surface_width,
                             alloc.height * 1.0 / surface_height)
        else:
            self._zoom = 1.0

        self._center_target_point()
        self._center_anchor_point()
        self._update_adjustments()
        self.queue_draw()

    def zoom_original(self):
        self._zoom = 1
        self._center_if_small()
        self._update_adjustments()
        self.queue_draw()

    def _move_anchor_to_target(self, prev_target_point):
        # Calculate the new anchor point, move it from the previous
        # target to the new one.

        prev_anchor_scaled = (self._anchor_point[0] * self._zoom,
                              self._anchor_point[1] * self._zoom)

        # This vector is the top left coordinate of the scaled image.
        scaled_image_topleft = (prev_target_point[0] - prev_anchor_scaled[0],
                                prev_target_point[1] - prev_anchor_scaled[1])

        anchor_scaled = (self._target_point[0] - scaled_image_topleft[0],
                         self._target_point[1] - scaled_image_topleft[1])

        self._anchor_point = (int(anchor_scaled[0] * 1.0 / self._zoom),
                              int(anchor_scaled[1] * 1.0 / self._zoom))

    def start_dragtouch(self, coords):
        self._in_dragtouch = True

        prev_target_point = self._target_point

        # Set target point to the relative coordinates of this view.
        alloc = self.get_allocation()
        self._target_point = (coords[1], coords[2])

        self._move_anchor_to_target(prev_target_point)
        self.queue_draw()

    def update_dragtouch(self, coords):
        # Drag touch will be replaced by zoom touch if another finger
        # is placed over the display.  When the user finishes zoom
        # touch, it will probably remove one finger after the other,
        # and this method will be called.  In that probable case, we
        # need to start drag touch again.
        if not self._in_dragtouch:
            self.start_dragtouch(coords)
            return

        self._target_point = (coords[1], coords[2])
        self._update_adjustments()
        self.queue_draw()

    def finish_dragtouch(self, coords):
        self._in_dragtouch = False
        self._center_if_small()
        self._update_adjustments()

    def start_zoomtouch(self, center):
        self._in_zoomtouch = True
        self._zoomtouch_scale = 1

        # Zoom touch replaces drag touch.
        self._in_dragtouch = False

        prev_target_point = self._target_point

        # Set target point to the relative coordinates of this view.
        alloc = self.get_allocation()
        self._target_point = (center[1] - alloc.x, center[2] - alloc.y)

        self._move_anchor_to_target(prev_target_point)
        self.queue_draw()

    def update_zoomtouch(self, center, scale):
        self._zoomtouch_scale = scale

        # Set target point to the relative coordinates of this view.
        alloc = self.get_allocation()
        self._target_point = (center[1] - alloc.x, center[2] - alloc.y)

        self.queue_draw()

    def finish_zoomtouch(self):
        self._in_zoomtouch = False

        # Apply zoom
        self._zoom = self._zoom * self._zoomtouch_scale
        self._zoomtouch_scale = 1

        # Restrict zoom values
        if self._zoom < ZOOM_MIN:
            self._zoom = ZOOM_MIN
        elif self._zoom > ZOOM_MAX:
            self._zoom = ZOOM_MAX

        self._center_if_small()
        self._update_adjustments()
        self.queue_draw()

    def rotate_anticlockwise(self):
        self._surface = _rotate_surface(self._surface, -1)

        # Recalculate the anchor point to make it relative to the new
        # top left corner.
        self._anchor_point = (
            self._anchor_point[1],
            self._surface.get_height() - self._anchor_point[0])

        self._update_adjustments()
        self.queue_draw()

    def rotate_clockwise(self):
        self._surface = _rotate_surface(self._surface, 1)

        # Recalculate the anchor point to make it relative to the new
        # top left corner.
        self._anchor_point = (
            self._surface.get_width() - self._anchor_point[1],
            self._anchor_point[0])

        self._update_adjustments()
        self.queue_draw()

    def __draw_cb(self, widget, ctx):

        # If the image surface is not set, it reads it from the file
        # location.  If the file location is not set yet, it just
        # returns.
        if self._surface is None:
            if self._file_location is None:
                return
            self._surface = _surface_from_file(self._file_location, ctx)

        if self._zoom is None:
            self.zoom_to_fit()

        # If no target point was set via pinch-to-zoom, default to the
        # center of the screen.
        if self._target_point is None:
            self._center_target_point()

        # If no anchor point was set via pinch-to-zoom, default to the
        # center of the surface.
        if self._anchor_point is None:
            self._center_anchor_point()
            self._update_adjustments()

        ctx.translate(*self._target_point)
        zoom_absolute = self._zoom * self._zoomtouch_scale
        ctx.scale(zoom_absolute, zoom_absolute)

        ctx.translate(self._anchor_point[0] * -1, self._anchor_point[1] * -1)

        ctx.set_source_surface(self._surface, 0, 0)

        # Perform faster draw if the view is zooming or scrolling via
        # mouse or touch.
        if self._in_zoomtouch or self._in_dragtouch or self._in_scrolling:
            ctx.get_source().set_filter(cairo.FILTER_NEAREST)

        ctx.paint()
