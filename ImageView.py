# Copyright (C) 2008, One Laptop Per Child
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

import gtk
from gtk import gdk
import cairo
import gobject

import sys
import logging

import random

class ImageViewer(gtk.DrawingArea):
    __gsignals__ = {
        'expose-event':   'override',
        'zoom-changed': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([])),
        'angle-changed': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([]))
    }

    __gproperties__ = {
        'zoom':    (gobject.TYPE_FLOAT, 
            'Zoom Factor', 'Factor of zoom', 
            0, 4, 1, gobject.PARAM_READWRITE),
        'angle':    (gobject.TYPE_INT,
            'Angle',    'Angle of rotation',
            0, 360, 0, gobject.PARAM_READWRITE),
        'file_location':   (gobject.TYPE_STRING,
            'File Location', 'Location of the image file',
            '', gobject.PARAM_READWRITE)
    }

    def __init__(self):
        gtk.DrawingArea.__init__(self)
        self.set_app_paintable(True)

        self.pixbuf = None
        self.zoom = None
        self.file_location = None
        self._temp_pixbuf = None
        self._image_changed_flag = True
        self._optimal_zoom_flag = True

        self.angle = 0


    def do_get_property(self, property):
        if property.name == 'zoom':
            return self.zoom
        elif property.name == 'angle':
            return self.angle
        elif property.name == 'file_location':
            return self.file_location
        else:
            raise AttributeError, 'unknown property %s' % property.name

    def do_set_property(self, property, value):
        if property.name == 'zoom':
            self.set_zoom(value)
        elif property.name == 'angle':
            self.set_angle(value)
        elif property.name == 'file_location':
            self.set_file_location(value)
        else:
            raise AttributeError, 'unknown property %s' % property.name

    def calculate_optimal_zoom(self, width = None, height = None, pixbuf = None):
        # This tries to figure out a best fit model
        # If the image can fit in, we show it in 1:1, 
        # in any other case we show it in a fit to screen way

        if pixbuf == None:
            pixbuf = self.pixbuf

        if width == None or height == None:
            rect =  self.parent.get_allocation()
            width = rect.width
            height = rect.height

        if width < pixbuf.get_width() or height < pixbuf.get_height():
            # Image is larger than allocated size
            zoom = min(width/pixbuf.get_width(), height/pixbuf.get_height())
        else:
            zoom = 1

        self._optimal_zoom_flag = True

        return zoom - 0.02 #XXX: Hack

    #def do_size_request(self, requisition):
    #    requisition.width = self.pixbuf.get_width()
    #    requisition.height = self.pixbuf.get_height()

    def do_expose_event(self, event):
        ctx = self.window.cairo_create()

        ctx.rectangle(event.area.x, event.area.y, 
            event.area.width, event.area.height)
        ctx.clip()
        self.draw(ctx)

    def draw(self, ctx):
        if not self.pixbuf:
            return
        if self.zoom == None:
            self.zoom = self.calculate_optimal_zoom()
        
        if self._temp_pixbuf == None or self._image_changed_flag == True:
            width, height = self.rotate()
            self._temp_pixbuf = self._temp_pixbuf.scale_simple(width, height, gtk.gdk.INTERP_TILES)
            self._image_changed_flag = False

        rect = self.get_allocation()
        x = rect.x
        y = rect.y

        width = self._temp_pixbuf.get_width()
        height = self._temp_pixbuf.get_height()

        if self.parent:
            rect = self.parent.get_allocation()
            if rect.width > width:
                x = int(((rect.width - x) - width)/2)

            if rect.height > height:
                y = int(((rect.height - y) - height)/2)

        self.set_size_request(self._temp_pixbuf.get_width(),self._temp_pixbuf.get_height())

        ctx.set_source_pixbuf(self._temp_pixbuf, x, y)

        ctx.paint()


    def set_zoom(self, zoom):
        self._image_changed_flag = True
        self._optimal_zoom_flag = False
        self.zoom = zoom

        if self.window:
            alloc = self.get_allocation()
            rect = gdk.Rectangle(alloc.x, alloc.y, 
                alloc.width, alloc.height)
            self.window.invalidate_rect(rect, True)
            self.window.process_updates(True)

        self.emit('zoom-changed')

    def set_angle(self, angle):
        self._image_changed_flag = True
        self._optimal_zoom_flag = True

        self.angle = angle

        if self.window:
            alloc = self.get_allocation()
            rect = gdk.Rectangle(alloc.x, alloc.y,
                alloc.width, alloc.height)
            self.window.invalidate_rect(rect, True)
            self.window.process_updates(True)

        self.emit('angle-changed')



    def rotate(self):
        if self.angle == 0:
            rotate = gtk.gdk.PIXBUF_ROTATE_NONE
        elif self.angle == 90:
            rotate = gtk.gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE
        elif self.angle == 180:
            rotate = gtk.gdk.PIXBUF_ROTATE_UPSIDEDOWN
        elif self.angle == 270:
            rotate = gtk.gdk.PIXBUF_ROTATE_CLOCKWISE
        elif self.angle == 360:
            self.angle = 0
            rotate = gtk.gdk.PIXBUF_ROTATE_NONE
        else:
            logging.warning('Got unsupported rotate angle')
            pass
            
        self._temp_pixbuf = self.pixbuf.rotate_simple(rotate)
        if self._optimal_zoom_flag == True:
            self.zoom = self.calculate_optimal_zoom(pixbuf = self._temp_pixbuf)
        
        width = int(self._temp_pixbuf.get_width()*self.zoom)
        height = int(self._temp_pixbuf.get_height()*self.zoom)

        return (width, height)

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
        self.pixbuf = gtk.gdk.pixbuf_new_from_file(file_location)
        self.file_location = file_location
        self.zoom = None
        self._image_changed_flag = True

        if self.window:
            alloc = self.get_allocation()
            rect = gdk.Rectangle(alloc.x, alloc.y,
                alloc.width, alloc.height)
            self.window.invalidate_rect(rect, True)
            self.window.process_updates(True)


def update(view):
    #return view.zoom_out()
    angle = 90 * random.randint(0,4)
    view.set_angle(angle)

    return True



if __name__ == '__main__':
    window = gtk.Window()

    vadj = gtk.Adjustment()
    hadj = gtk.Adjustment()
    sw = gtk.ScrolledWindow(hadj, vadj)

    view = ImageViewer()

    view.set_file_location(sys.argv[1])


    sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)


    sw.add_with_viewport(view)
    window.add(sw)

    window.set_size_request(800,600)

    window.show_all()

    gobject.timeout_add(1000, update, view)

    gtk.main()

