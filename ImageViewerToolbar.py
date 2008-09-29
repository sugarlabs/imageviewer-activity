# Based on read-activity/readtoolbar.py
# Copyright (C) 2006, Red Hat, Inc.
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
from gettext import gettext as _
import re

import pango
import gobject
import gtk

from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.menuitem import MenuItem
from sugar.graphics import iconentry
from sugar.activity import activity


class ViewToolbar(gtk.Toolbar):
    __gtype_name__ = 'ViewToolbar'

    __gsignals__ = {
        'go-fullscreen': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([]))
    }

    def __init__(self, view):
        gtk.Toolbar.__init__(self)

        self._view = view
            
        self._zoom_out = ToolButton('zoom-out')
        self._zoom_out.set_tooltip(_('Zoom out'))
        self._zoom_out.connect('clicked', self._zoom_out_cb)
        self.insert(self._zoom_out, -1)
        self._zoom_out.show()

        self._zoom_in = ToolButton('zoom-in')
        self._zoom_in.set_tooltip(_('Zoom in'))
        self._zoom_in.connect('clicked', self._zoom_in_cb)
        self.insert(self._zoom_in, -1)
        self._zoom_in.show()

        self._zoom_tofit = ToolButton('zoom-best-fit')
        self._zoom_tofit.set_tooltip(_('Fit to window'))
        self._zoom_tofit.connect('clicked', self._zoom_tofit_cb)
        self.insert(self._zoom_tofit, -1)
        self._zoom_tofit.show()
        
        self._zoom_original = ToolButton('zoom-original')
        self._zoom_original.set_tooltip(_('Original size'))
        self._zoom_original.connect('clicked', self._zoom_original_cb)
        self.insert(self._zoom_original, -1)
        self._zoom_original.show()

        spacer = gtk.SeparatorToolItem()
        spacer.props.draw = False
        self.insert(spacer, -1)
        spacer.show()

        self._rotate_anticlockwise = ToolButton('rotate_anticlockwise')
        self._rotate_anticlockwise.set_tooltip(_('Rotate anticlockwise'))
        self._rotate_anticlockwise.connect('clicked', self._rotate_anticlockwise_cb)
        self.insert(self._rotate_anticlockwise, -1)
        self._rotate_anticlockwise.show()

        self._rotate_clockwise = ToolButton('rotate_clockwise')
        self._rotate_clockwise.set_tooltip(_('Rotate clockwise'))
        self._rotate_clockwise.connect('clicked', self._rotate_clockwise_cb)
        self.insert(self._rotate_clockwise, -1)
        self._rotate_clockwise.show()
        
        spacer = gtk.SeparatorToolItem()
        spacer.props.draw = False
        self.insert(spacer, -1)
        spacer.show()

        self._fullscreen = ToolButton('view-fullscreen')
        self._fullscreen.set_tooltip(_('Fullscreen'))
        self._fullscreen.connect('clicked', self._fullscreen_cb)
        self.insert(self._fullscreen, -1)
        self._fullscreen.show()


    def _zoom_in_cb(self, button):
        self._zoom_in.set_sensitive(self._view.zoom_in())
        self._zoom_out.set_sensitive(True)

    def _zoom_out_cb(self, button):
        self._zoom_out.set_sensitive(self._view.zoom_out())
        self._zoom_in.set_sensitive(True)

    def _zoom_tofit_cb(self, button):
        zoom = self._view.calculate_optimal_zoom()
        self._view.set_zoom(zoom)
        
    def _zoom_original_cb(self, button):
        self._view.set_zoom(1)

    def _rotate_anticlockwise_cb(self, button):
        angle = self._view.get_property('angle')
        self._view.set_angle(angle + 90)
        
    def _rotate_clockwise_cb(self, button):
        angle = self._view.get_property('angle')
        if angle == 0:
            angle = 360

        self._view.set_angle(angle - 90)        
    
    def _fullscreen_cb(self, button):
        self.emit('go-fullscreen')
