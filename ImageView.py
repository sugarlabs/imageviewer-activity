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

import cairo

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import GObject

ZOOM_STEP = 0.05
ZOOM_MAX = 4
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


class ImageViewer(Gtk.DrawingArea):
    def __init__(self):
        Gtk.DrawingArea.__init__(self)

        self._file_location = None
        self._surface = None
        self._zoom = None

        self.connect('draw', self.__draw_cb)

    def set_file_location(self, file_location):
        self._file_location = file_location
        self.queue_draw()

    def set_zoom(self, zoom):
        self._zoom = zoom
        self.queue_draw()

    def get_zoom(self):
        return self._zoom

    def zoom_in(self):
        if self._zoom + ZOOM_STEP > ZOOM_MAX:
            return
        self._zoom += ZOOM_STEP
        self.queue_draw()

    def zoom_out(self):
        if self._zoom - ZOOM_STEP < ZOOM_MIN:
            return
        self._zoom -= ZOOM_MIN
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
        self.queue_draw()

    def zoom_equal(self):
        self._zoom = 1
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

        # FIXME investigate
        ctx.set_antialias(cairo.ANTIALIAS_NONE)

        # Scale and center the image according to the current zoom.

        scaled_width = int(self._surface.get_width() * self._zoom)
        scaled_height = int(self._surface.get_height() * self._zoom)

        alloc = self.get_allocation()
        x_offset = (alloc.width * 1.0 - scaled_width) / 2
        y_offset = (alloc.height * 1.0 - scaled_height) / 2

        ctx.translate(x_offset, y_offset)
        ctx.scale(self._zoom, self._zoom)
        ctx.set_source_surface(self._surface, 0, 0)

        # FIXME investigate
        ctx.get_source().set_filter(cairo.FILTER_NEAREST)

        ctx.paint()


if __name__ == '__main__':
    import sys

    window = Gtk.Window()
    window.connect("destroy", Gtk.main_quit)

    view = ImageViewer()
    view.set_file_location(sys.argv[1])
    window.add(view)
    view.show()

    window.set_size_request(800, 600)
    window.show()

    Gtk.main()
