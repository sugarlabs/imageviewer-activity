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

# The sharing bits have been taken from ReadEtexts


from sugar4.activity import activity
import logging

from gettext import gettext as _

import time
import os
from gi.repository import GLib
from gi.repository import Gdk
from gi.repository import Gtk

from sugar4.graphics.alert import NotifyAlert

from sugar4 import mime
from sugar4.graphics.toolbutton import ToolButton
from sugar4.graphics.toolbarbox import ToolbarBox
from sugar4.graphics.icon import Icon
from sugar4.activity.widgets import ActivityToolbarButton
from sugar4.activity.widgets import StopButton
from sugar4.graphics import style
from sugar4.graphics.alert import Alert
from sugar4.datastore import datastore

import collabwrapper
import ImageView


class ProgressAlert(Alert):
    """
    Progress alert with a progressbar - to show the advance of a task
    """

    def __init__(self, timeout=5, **kwargs):
        Alert.__init__(self, **kwargs)

        self._pb = Gtk.ProgressBar()
        self._pb.set_hexpand(True)
        self._msg_box.append(self._pb)
        self._pb.set_fraction(0.0)

    def set_fraction(self, fraction):
        # update only by 10% fractions
        if int(fraction * 100) % 10 == 0:
            self._pb.set_fraction(fraction)


class ImageViewerActivity(activity.Activity):

    def __init__(self, handle):
        activity.Activity.__init__(self, handle)
        self._object_id = handle.object_id

        try:
            self._collab = collabwrapper.CollabWrapper(self)
            self._collab.incoming_file.connect(self.__incoming_file_cb)
            self._collab.buddy_joined.connect(self.__buddy_joined_cb)
            self._collab.joined.connect(self.__joined_cb)
        except Exception as e:
            logging.warning("CollabWrapper init failed (no Sugar session?): %s", e)
            self._collab = None

        self._needs_file = False  # Set to true when we join
        

        # Status of temp file used for write_file:
        self._tempfile = None
        self._close_requested = False

        self._zoom_out_button = None
        self._zoom_in_button = None
        self.previous_image_button = None
        self.next_image_button = None

        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.ALWAYS,
                                        Gtk.PolicyType.ALWAYS)
        # disable sharing until a file is opened
        self.max_participants = 1

        # Don't use the default kinetic scrolling, let the view do the
        # drag-by-touch and pinch-to-zoom logic.
        self.scrolled_window.set_kinetic_scrolling(False)

        self.view = ImageView.ImageViewer()

        self._image_list = []
        
        # 1. Touch/Drag Controller (replaces TOUCH_MASK)
        drag_controller = Gtk.GestureDrag()
        drag_controller.connect('drag-begin', self.__drag_begin_cb)
        drag_controller.connect('drag-update', self.__drag_update_cb)
        drag_controller.connect('drag-end', self.__drag_end_cb)
        self.view.add_controller(drag_controller)

        # 2. Keyboard Controller (replaces key-press-event)
        key_controller = Gtk.EventControllerKey()
        key_controller.connect('key-pressed', self.__key_pressed_cb)
        self.add_controller(key_controller)

        # 3. Zoom Controller (replaces SugarGestures)
        zoom_controller = Gtk.GestureZoom()
        zoom_controller.connect('begin', self.__zoom_begin_cb)
        zoom_controller.connect('scale-changed', self.__zoom_scale_changed_cb)
        zoom_controller.connect('end', self.__zoom_end_cb)
        self.view.add_controller(zoom_controller)

        self.scrolled_window.set_child(self.view)

        self._progress_alert = None

        toolbar_box = ToolbarBox()
        self._add_toolbar_buttons(toolbar_box)
        self.set_toolbar_box(toolbar_box)

        if self._object_id is None or not self._jobject.file_path:
            # start new, or resume empty
            
            empty_widgets = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            empty_widgets.add_css_class('imageviewer-empty')

            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(
                '.imageviewer-empty {{ background-color: {}; }}'.format(
                    style.COLOR_WHITE.get_html()).encode())
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            mvbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            
            mvbox.set_spacing(style.DEFAULT_PADDING)
            mvbox.set_vexpand(True)
            mvbox.set_valign(Gtk.Align.CENTER)
            mvbox.set_halign(Gtk.Align.CENTER)

            vbox.append(mvbox)

            image_icon = Icon(pixel_size=style.LARGE_ICON_SIZE,
                              icon_name='imageviewer',
                              stroke_color=style.COLOR_BUTTON_GREY.get_svg(),
                              fill_color=style.COLOR_TRANSPARENT.get_svg())
            mvbox.append(image_icon)

            label = Gtk.Label(label='<span foreground="%s"><b>%s</b></span>' %
                              (style.COLOR_BUTTON_GREY.get_html(),
                               _('No image')))
            label.set_use_markup(True)
            mvbox.append(label)

            empty_widgets.append(vbox)
            
            self.set_canvas(empty_widgets)
            self.busy()
            GLib.idle_add(self._get_image_list)
        else:
            # opening an image, or our journal object with image
            self.set_canvas(self.scrolled_window)

        self.connect('notify::default-width', self._configure_cb)

        if self._collab:
            self._collab.setup()

    def __drag_begin_cb(self, controller, start_x, start_y):
        self.view.start_dragtouch((start_x, start_y))

    def __drag_update_cb(self, controller, offset_x, offset_y):
        success, start_x, start_y = controller.get_start_point()
        if success:
            self.view.update_dragtouch((start_x + offset_x, start_y + offset_y))

    def __drag_end_cb(self, controller, offset_x, offset_y):
        success, start_x, start_y = controller.get_start_point()
        if success:
            self.view.finish_dragtouch((start_x + offset_x, start_y + offset_y))

    def __zoom_begin_cb(self, controller, sequence):
        success, x, y = controller.get_bounding_box_center()
        if success:
            self.view.start_zoomtouch((x, y))

    def __zoom_scale_changed_cb(self, controller, scale):
        success, x, y = controller.get_bounding_box_center()
        if success:
            self.view.update_zoomtouch((x, y), scale)

    def __zoom_end_cb(self, controller, sequence):
        self.view.finish_zoomtouch()

    def __key_pressed_cb(self, controller, keyval, keycode, state):
        key_name = Gdk.keyval_name(keyval)
        if key_name == "Left":
            self._change_image(-1)
        elif key_name == "Right":
            self._change_image(1)
        elif state & Gdk.ModifierType.CONTROL_MASK:
            if key_name == "q":
                self.close()
        return True

    def _get_image_list(self):
        value = mime.GENERIC_TYPE_IMAGE
        mime_types = mime.get_generic_type(value).mime_types
        try:
            (self.image_list, self.image_count) = datastore.find({'mime_type':mime_types})
        except Exception as e:
            print("Warning: Could not connect to Datastore to fetch images: %s" % e)
            self.image_list, self.image_count = [], 0
            
        self.unbusy()

        if self.image_count == 0:
            # start new, or resume empty; with no images in journal
            # leave the "No image" message visible
            return False

        if self.image_count > 1:
            # start new, or resume empty; with more than one image in journal
            # add image choosing buttons to toolbar box
            self.list_set_visible(self._traverse_widgets, True)

        # start new, or resume empty; with at least one image in journal
        # display the first image
        self.current_image_index = 0
        self._change_image(0)
        self.traverse_update_sensitive()

        self.set_canvas(self.scrolled_window)

        return False

    def _add_toolbar_buttons(self, toolbar_box):
        self._seps = []
        self._image_buttons = []

        self.activity_button = ActivityToolbarButton(self)
        toolbar_box.toolbar.prepend(self.activity_button)

        self._zoom_out_button = ToolButton('zoom-out')
        self._zoom_out_button.set_tooltip(_('Zoom out'))
        self._image_buttons.append(self._zoom_out_button)
        self._zoom_out_button.connect('clicked', self.__zoom_out_cb)
        toolbar_box.toolbar.append(self._zoom_out_button)

        self._zoom_in_button = ToolButton('zoom-in')
        self._zoom_in_button.set_tooltip(_('Zoom in'))
        self._image_buttons.append(self._zoom_in_button)
        self._zoom_in_button.connect('clicked', self.__zoom_in_cb)
        toolbar_box.toolbar.append(self._zoom_in_button)

        zoom_tofit_button = ToolButton('zoom-best-fit')
        zoom_tofit_button.set_tooltip(_('Fit to window'))
        self._image_buttons.append(zoom_tofit_button)
        zoom_tofit_button.connect('clicked', self.__zoom_tofit_cb)
        toolbar_box.toolbar.append(zoom_tofit_button)

        zoom_original_button = ToolButton('zoom-original')
        zoom_original_button.set_tooltip(_('Original size'))
        self._image_buttons.append(zoom_original_button)
        zoom_original_button.connect('clicked', self.__zoom_original_cb)
        toolbar_box.toolbar.append(zoom_original_button)

        fullscreen_button = ToolButton('view-fullscreen')
        fullscreen_button.set_tooltip(_('Fullscreen'))
        self._image_buttons.append(fullscreen_button)
        fullscreen_button.connect('clicked', self.__fullscreen_cb)
        toolbar_box.toolbar.append(fullscreen_button)
        
        self._seps.append(Gtk.Separator())
        toolbar_box.toolbar.append(self._seps[-1])

        rotate_anticlockwise_button = ToolButton('rotate_anticlockwise')
        rotate_anticlockwise_button.set_tooltip(_('Rotate anticlockwise'))
        self._image_buttons.append(rotate_anticlockwise_button)
        rotate_anticlockwise_button.connect('clicked',
                                            self.__rotate_anticlockwise_cb)
        toolbar_box.toolbar.append(rotate_anticlockwise_button)

        rotate_clockwise_button = ToolButton('rotate_clockwise')
        rotate_clockwise_button.set_tooltip(_('Rotate clockwise'))
        self._image_buttons.append(rotate_clockwise_button)
        rotate_clockwise_button.connect('clicked', self.__rotate_clockwise_cb)
        toolbar_box.toolbar.append(rotate_clockwise_button)

        self.list_set_sensitive(self._image_buttons, False)

        self._traverse_widgets = []
        separator = Gtk.Separator()
        self._seps.append(separator)
        toolbar_box.toolbar.append(separator)
        self._traverse_widgets.append(separator)

        self.previous_image_button = ToolButton('go-previous-paired')
        self.previous_image_button.set_tooltip(_('Previous Image'))
        self.previous_image_button.props.sensitive = False
        self.previous_image_button.connect('clicked',
                                           self.__previous_image_cb)
        toolbar_box.toolbar.append(self.previous_image_button)
        self._traverse_widgets.append(self.previous_image_button)

        self.next_image_button = ToolButton('go-next-paired')
        self.next_image_button.set_tooltip(_('Next Image'))
        self.next_image_button.props.sensitive = False
        self.next_image_button.connect('clicked', self.__next_image_cb)
        toolbar_box.toolbar.append(self.next_image_button)
        self._traverse_widgets.append(self.next_image_button)

        self.list_set_visible(self._traverse_widgets, False)
        
        separator = Gtk.Box()
        separator.set_hexpand(True)
        toolbar_box.toolbar.append(separator)

        stop_button = StopButton(self)
        toolbar_box.toolbar.append(stop_button)

    def _configure_cb(self, widget=None, pspec=None):
        if self.get_width() <= style.GRID_CELL_SIZE * 12:
            self.list_set_visible(self._seps, False)
        else:
            self.list_set_visible(self._seps, True)

    def _update_zoom_buttons(self):
        self._zoom_in_button.set_sensitive(self.view.can_zoom_in())
        self._zoom_out_button.set_sensitive(self.view.can_zoom_out())

    def _change_image(self, delta):
        # boundary conditions
        if self.current_image_index == 0 and delta == -1:
            return
        if self.current_image_index == self.image_count - 1 and delta == 1:
            return

        self.current_image_index += delta
        self.traverse_update_sensitive()

        jobject = self.image_list[self.current_image_index]
        self._object_id = jobject.object_id
        self.read_file(jobject.file_path)

    def __previous_image_cb(self, button):
        if self.current_image_index > 0:
            self._change_image(-1)

    def __next_image_cb(self, button):
        if self.current_image_index < self.image_count:
            self._change_image(1)

    def __zoom_in_cb(self, button):
        self.view.zoom_in()
        self._update_zoom_buttons()

    def __zoom_out_cb(self, button):
        self.view.zoom_out()
        self._update_zoom_buttons()

    def __zoom_tofit_cb(self, button):
        self.view.zoom_to_fit()
        self._update_zoom_buttons()

    def __zoom_original_cb(self, button):
        self.view.zoom_original()
        self._update_zoom_buttons()

    def __rotate_anticlockwise_cb(self, button):
        self.view.rotate_anticlockwise()

    def __rotate_clockwise_cb(self, button):
        self.view.rotate_clockwise()

    def __fullscreen_cb(self, button):
        self.fullscreen()

    def update_current_image_index(self):
        for image in self.image_list:
            if image.object_id == self._object_id:
                jobject = image
                break
        else:
            return False
        self.current_image_index = self.image_list.index(jobject)
        return True

    def list_set_visible(self, widgets, visible):
        for widget in widgets:
            widget.set_visible(visible)

    def list_set_sensitive(self, widgets, sensitive):
        for widget in widgets:
            widget.set_sensitive(sensitive)

    def traverse_update_sensitive(self):
        if self.image_count <= 1:
            return

        if self.current_image_index == 0:
            self.next_image_button.props.sensitive = True
            self.previous_image_button.props.sensitive = False
        elif self.current_image_index == self.image_count - 1:
            self.previous_image_button.props.sensitive = True
            self.next_image_button.props.sensitive = False
        else:
            self.next_image_button.props.sensitive = True
            self.previous_image_button.props.sensitive = True

    def get_data(self):
        return None

    def set_data(self, data):
        pass

    def get_preview(self):
        if self.metadata.get('preview', None) is None:
            activity.Activity.get_preview(self)

    def read_file(self, file_path):
        if self._object_id is None or self.shared_activity:
            # read_file is call because the canvas is visible
            # but we need check if is not the case of empty file
            return

        # enable collaboration
        self.activity_button.page.share.props.sensitive = True

        tempfile = os.path.join(self.get_activity_root(), 'instance',
                                'tmp%f' % time.time())

        os.link(file_path, tempfile)
        self._tempfile = tempfile

        self.view.set_file_location(tempfile)
        self.list_set_sensitive(self._image_buttons, True)

        zoom = self.metadata.get('zoom', None)
        if zoom is not None:
            self.view.set_zoom(float(zoom))

    def write_file(self, file_path):
        if self._tempfile:
            self.metadata['zoom'] = str(self.view.get_zoom())
            if self._close_requested:
                os.link(self._tempfile, file_path)
                os.unlink(self._tempfile)
                self._tempfile = None
        else:
            raise NotImplementedError

    def can_close(self):
        self._close_requested = True
        return True

    def __incoming_file_cb(self, collab, ft, desc):
        logging.debug('__incoming_file_cb with need %r', self._needs_file)
        if not self._needs_file:
            return

        self._progress_alert = ProgressAlert()
        self._progress_alert.props.title = _('Receiving image...')
        self.add_alert(self._progress_alert)

        self._needs_file = False
        file_path = os.path.join(self.get_activity_root(), 'instance',
                                 '%i' % time.time())
        ft.connect('notify::state', self.__file_notify_state_cb)
        ft.connect('notify::transfered_bytes',
                     self.__file_transfered_bytes_cb)
        ft.accept_to_file(file_path)

    def __file_notify_state_cb(self, ft, pspec):
        logging.debug('__file_notify_state %r', ft.props.state)
        if ft.props.state != collabwrapper.FT_STATE_COMPLETED:
            return

        file_path = ft.props.output
        logging.debug("Saving file %s to datastore...", file_path)
        self._jobject.file_path = file_path
        datastore.write(self._jobject, transfer_ownership=True)

        if self._progress_alert is not None:
            self.remove_alert(self._progress_alert)
            self._progress_alert = None

        GLib.idle_add(self.__set_file_idle_cb, self._jobject.object_id)

    def __set_file_idle_cb(self, object_id):
        dsobj = datastore.get(object_id)
        self._tempfile = dsobj.file_path
        """ This method is used when join a collaboration session """
        self.view.set_file_location(self._tempfile)
        try:
            zoom = int(self.metadata.get('zoom', '0'))
            if zoom > 0:
                self.view.set_zoom(zoom)
        except Exception:
            pass
        self.set_canvas(self.scrolled_window)
        self.scrolled_window.set_visible(True)
        self.list_set_sensitive(self._image_buttons, True)
        return False

    def __file_transfered_bytes_cb(self, file, pspec):
        total = file.file_size
        bytes_downloaded = file.props.transfered_bytes
        fraction = bytes_downloaded / total
        self._progress_alert.set_fraction(fraction)

    def __buddy_joined_cb(self, collab, buddy):
        logging.debug('__buddy_joined_cb %r', buddy.props.nick)
        if self._tempfile is None:
            return  # we have nothing to share
        self._collab.send_file_file(buddy, self._tempfile, None)

    def __joined_cb(self, collab):
        logging.debug('I joined!')
        # Somebody will send us a file, just wait
        self._needs_file = True

    def _alert(self, title, text=None):
        alert = NotifyAlert(timeout=5)
        alert.props.title = title
        alert.props.msg = text
        self.add_alert(alert)
        alert.connect('response', self._alert_cancel_cb)

    def _alert_cancel_cb(self, alert, response_id):
        self.remove_alert(alert)
