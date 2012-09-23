from gi.repository import Gtk
from gi.repository import GObject
from gettext import gettext as _


class ProgressDialog(Gtk.Dialog):

    def __init__(self, parent):
        GObject.GObject.__init__(self, _('Downloading...'), parent, \
                Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, \
                (Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT))

        self._activity = parent

        self.connect('response', self._response_cb)

        self._pb = Gtk.ProgressBar()
        self._pb.set_text(_('Retrieving shared image, please wait...'))
        self.vbox.add(self._pb)

    def _response_cb(self, dialog, response_id):
        if response_id == Gtk.ResponseType.REJECT:
            self._activity.close()
        else:
            pass

    def set_fraction(self, fraction):
        self._pb.set_fraction(fraction)
