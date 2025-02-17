import sys
import os
import functools
import traceback
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from yapsy.PluginManager import PluginManager

from core.trace_data import TraceData
from core.bookmark import Bookmark
from core import trace_files
from core.filter_and_find import find
from core.filter_and_find import filter_trace
from core.filter_and_find import TraceField
from core.syntax import AsmHighlighter
from core import prefs


class MainWindow(QtWidgets.QMainWindow):
    """MainWindow class

    Attributes:
        trace_data (TraceData): TraceData object
        filtered_trace (list): Filtered trace
    """
    def __init__(self):
        """Inits MainWindow, UI and plugins"""
        super(MainWindow, self).__init__()
        self.trace_data = TraceData()
        self.filtered_trace = None
        self.init_plugins()
        self.init_ui()
        if len(sys.argv) > 1:
            self.open_trace(sys.argv[1])

    def dragEnterEvent(self, event):
        """QMainWindow method reimplementation for file drag."""
        event.accept()

    def dropEvent(self, event):
        """QMainWindow method reimplementation for file drop."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local_file = url.toLocalFile()
                if os.path.isfile(local_file):
                    self.open_trace(local_file)

    def init_plugins(self):
        """Inits plugins"""
        self.manager = PluginManager()
        for plugin in self.manager.getAllPlugins():
            print_debug("Plugin found: %s" % plugin.name)
        self.manager.setPluginPlaces(["plugins"])
        self.manager.collectPlugins()

    def init_plugins_menu(self):
        """Inits plugins menu"""
        self.plugins_topmenu.clear()
        reload_action = QtWidgets.QAction("Reload plugins", self)
        func = functools.partial(self.reload_plugins)
        reload_action.triggered.connect(func)
        self.plugins_topmenu.addAction(reload_action)
        self.plugins_topmenu.addSeparator()

        for plugin in self.manager.getAllPlugins():
            action = QtWidgets.QAction(plugin.name, self)
            func = functools.partial(self.execute_plugin, plugin)
            action.triggered.connect(func)
            self.plugins_topmenu.addAction(action)

    def reload_plugins(self):
        """Reloads plugins"""
        self.init_trace_table_menu()
        self.init_plugins_menu()
        self.init_plugins()

    def init_ui(self):
        """Inits UI"""
        uic.loadUi("gui/mainwindow.ui", self)

        title = prefs.PACKAGE_NAME + " " + prefs.PACKAGE_VERSION
        self.setWindowTitle(title)

        self.filter_button.clicked.connect(self.on_filter_clicked)
        self.filter_check_box.stateChanged.connect(self.on_filter_check_box_state_changed)

        self.find_next_button.clicked.connect(lambda: self.on_find_clicked(1))
        self.find_prev_button.clicked.connect(lambda: self.on_find_clicked(-1))

        self.regs_list.currentItemChanged.connect(self.on_reg_list_selection_changed)
        self.mem_list.currentItemChanged.connect(self.on_mem_list_selection_changed)

        # accept file drops
        self.setAcceptDrops(True)

        # make trace table wider than regs&mem
        self.splitter1.setSizes([1400, 100])
        self.splitter2.setSizes([600, 100])

        # Init trace table
        self.trace_table.setColumnCount(len(prefs.TRACE_LABELS))
        self.trace_table.setHorizontalHeaderLabels(prefs.TRACE_LABELS)
        self.trace_table.itemSelectionChanged.connect(self.on_trace_table_selection_changed)
        self.trace_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.trace_table.customContextMenuRequested.connect(
            self.trace_table_context_menu_event
        )

        # Init bookmark table
        self.bookmark_table.setColumnCount(len(prefs.BOOKMARK_LABELS))
        self.bookmark_table.setHorizontalHeaderLabels(prefs.BOOKMARK_LABELS)
        self.bookmark_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.bookmark_table.customContextMenuRequested.connect(
            self.bookmark_table_context_menu_event
        )

        self.bookmark_menu = QtWidgets.QMenu(self)

        go_action = QtWidgets.QAction("Go to bookmark", self)
        go_action.triggered.connect(self.go_to_bookmark)
        self.bookmark_menu.addAction(go_action)

        delete_bookmarks_action = QtWidgets.QAction("Delete bookmark(s)", self)
        delete_bookmarks_action.triggered.connect(self.delete_bookmarks)
        self.bookmark_menu.addAction(delete_bookmarks_action)

        # Menu
        exit_action = QtWidgets.QAction("&Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Exit application")
        exit_action.triggered.connect(self.close)

        open_trace_action = QtWidgets.QAction("&Open trace..", self)
        open_trace_action.setStatusTip("Open trace")
        open_trace_action.triggered.connect(self.dialog_open_trace)

        self.save_trace_action = QtWidgets.QAction("&Save trace", self)
        self.save_trace_action.setShortcut("Ctrl+S")
        self.save_trace_action.setStatusTip("Save trace")
        self.save_trace_action.triggered.connect(self.save_trace)
        self.save_trace_action.setEnabled(False)

        save_trace_as_action = QtWidgets.QAction("&Save trace as..", self)
        save_trace_as_action.setStatusTip("Save trace as..")
        save_trace_as_action.triggered.connect(self.dialog_save_trace_as)

        save_trace_as_json_action = QtWidgets.QAction("&Save trace as JSON..", self)
        save_trace_as_json_action.setStatusTip("Save trace as JSON..")
        save_trace_as_json_action.triggered.connect(self.dialog_save_trace_as_json)

        file_menu = self.menu_bar.addMenu("&File")
        file_menu.addAction(open_trace_action)
        file_menu.addAction(self.save_trace_action)
        file_menu.addAction(save_trace_as_action)
        file_menu.addAction(save_trace_as_json_action)
        file_menu.addAction(exit_action)

        self.plugins_topmenu = self.menu_bar.addMenu("&Plugins")

        clear_bookmarks_action = QtWidgets.QAction("&Clear bookmarks", self)
        clear_bookmarks_action.setStatusTip("Clear bookmarks")
        clear_bookmarks_action.triggered.connect(self.clear_bookmarks)

        bookmarks_menu = self.menu_bar.addMenu("&Bookmarks")
        bookmarks_menu.addAction(clear_bookmarks_action)

        # Init right click menu for trace table
        self.init_trace_table_menu()
        self.init_plugins_menu()

        about_action = QtWidgets.QAction("&About", self)
        about_action.triggered.connect(self.show_about_dialog)

        about_menu = self.menu_bar.addMenu("&About")
        about_menu.addAction(about_action)

        if prefs.USE_SYNTAX_HIGHLIGHT:
            self.highlight = AsmHighlighter(self.log_text_edit.document())

        for field in prefs.FIND_FIELDS:
            self.find_combo_box.addItem(field)

        if prefs.SHOW_SAMPLE_FILTERS:
            for sample_filter in prefs.SAMPLE_FILTERS:
                self.filter_edit.addItem(sample_filter)

        self.filter_edit.keyPressEvent = self.on_filter_edit_key_pressed

        self.show()

    def init_trace_table_menu(self):
        """Initializes right click menu for trace table"""
        self.trace_table_menu = QtWidgets.QMenu(self)

        copy_action = QtWidgets.QAction("Print selected cells", self)
        copy_action.triggered.connect(self.trace_table_print_cells)
        self.trace_table_menu.addAction(copy_action)

        add_bookmark_action = QtWidgets.QAction("Add Bookmark", self)
        add_bookmark_action.triggered.connect(self.trace_table_create_bookmark)
        self.trace_table_menu.addAction(add_bookmark_action)

        plugins_menu = QtWidgets.QMenu("Plugins", self)

        for plugin in self.manager.getAllPlugins():
            action = QtWidgets.QAction(plugin.name, self)
            func = functools.partial(self.execute_plugin, plugin)
            action.triggered.connect(func)
            plugins_menu.addAction(action)
        self.trace_table_menu.addMenu(plugins_menu)

    def set_filter(self, filter_text):
        """Sets a a new filter for trace and filters trace"""
        try:
            self.filtered_trace = filter_trace(
                self.trace_data.trace,
                self.trace_data.regs,
                filter_text
            )
        except Exception as exc:
            print("Error on filter: " + str(exc))
            print(traceback.format_exc())

    def get_visible_trace(self):
        """Returns the trace that is currently shown on trace table"""
        if self.filter_check_box.isChecked() and self.filtered_trace is not None:
            return self.filtered_trace
        return self.trace_data.trace

    def bookmark_table_context_menu_event(self):
        """Context menu for bookmark table right click"""
        self.bookmark_menu.popup(QtGui.QCursor.pos())

    def dialog_open_trace(self):
        """Shows dialog to open trace file"""
        all_traces = "All traces (*.tvt *.trace32 *.trace64)"
        all_files = "All files (*.*)"
        filename = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open trace", "", all_traces + ";; " + all_files
        )[0]
        if filename:
            self.open_trace(filename)
            if self.trace_data:
                self.save_trace_action.setEnabled(True)

    def dialog_save_trace_as(self):
        """Shows a dialog to select a save file"""
        filename = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save trace as", "", "Trace Viewer traces (*.tvt);; All files (*.*)"
        )[0]
        print_debug("Save trace as: " + filename)
        if filename and trace_files.save_as_tv_trace(self.trace_data, filename):
            self.trace_data.filename = filename
            self.save_trace_action.setEnabled(True)

    def dialog_save_trace_as_json(self):
        """Shows a dialog to save trace to JSON file"""
        filename = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save as JSON", "", "JSON files (*.txt);; All files (*.*)"
        )[0]
        print_debug("Save trace as: " + filename)
        if filename:
            trace_files.save_as_json(self.trace_data, filename)

    def execute_plugin(self, plugin):
        """Executes a plugin and updates tables"""
        print_debug("Executing a plugin: %s" % plugin.name)
        selected_row_ids = self.get_selected_row_ids(self.trace_table)
        try:
            plugin.plugin_object.execute(self, self.trace_data, selected_row_ids)
        except Exception:
            print_debug("Error in plugin. Check log for details.")
            self.print("Error in plugin:")
            self.print(traceback.format_exc())
        finally:
            if prefs.USE_SYNTAX_HIGHLIGHT:
                self.highlight.rehighlight()

    def on_filter_edit_key_pressed(self, event):
        """Checks if enter is pressed on filterEdit"""
        key = event.key()
        if key == QtCore.Qt.Key_Return:
            self.on_filter_clicked()
        QtWidgets.QComboBox.keyPressEvent(self.filter_edit, event)

    def on_filter_check_box_state_changed(self):
        """Callback function for state change of filter checkbox"""
        self.update_trace_table()

    def on_find_clicked(self, direction):
        """Find next or prev button clicked"""

        row = self.trace_table.currentRow()
        if row < 0:
            row = 0

        keyword = self.search_edit.text()
        index = self.find_combo_box.currentIndex()
        if index == 0:
            field = TraceField.DISASM
        elif index == 1:
            field = TraceField.REGS
        elif index == 2:
            field = TraceField.MEM
        elif index == 3:
            field = TraceField.COMMENT
        elif index == 4:
            field = TraceField.ANY

        try:
            row_number = find(
                trace=self.get_visible_trace(),
                field=field,
                keyword=keyword,
                start_row=row + direction,
                direction=direction,
            )
        except Exception as exc:
            print_debug("Error on find: " + str(exc))
            self.print(traceback.format_exc())
            return

        if row_number is not None:
            self.goto_row(self.trace_table, row_number)
            self.select_row(self.trace_table, row_number)
        else:
            print_debug(
                "%s not found (row %d, direction %d)" % (keyword, row, direction)
            )

    def on_filter_clicked(self):
        """Sets a filter and filters trace data"""
        filter_text = self.filter_edit.currentText()
        print_debug("Set filter: %s" % filter_text)
        self.set_filter(filter_text)
        if not self.filter_check_box.isChecked():
            self.filter_check_box.setChecked(True)
        else:
            self.update_trace_table()

    def on_trace_table_cell_edited(self, item):
        """Called when any cell is edited on trace table"""
        table = self.trace_table
        cell_type = item.whatsThis()
        if cell_type == "comment":
            row = table.currentRow()
            if row < 0:
                print_debug("Error, could not edit trace.")
                return
            row_id = int(table.item(row, 0).text())
            self.trace_data.set_comment(item.text(), row_id)
        else:
            print_debug("Only comment editing allowed for now...")

    def on_bookmark_table_cell_edited(self, item):
        """Called when any cell is edited on bookmark table"""
        cell_type = item.whatsThis()
        bookmarks = self.trace_data.get_bookmarks()
        row = self.bookmark_table.currentRow()
        if row < 0:
            print_debug("Error, could not edit bookmark.")
            return
        if cell_type == "startrow":
            bookmarks[row].startrow = int(item.text())
        elif cell_type == "endrow":
            bookmarks[row].endrow = int(item.text())
        elif cell_type == "address":
            bookmarks[row].addr = item.text()
        elif cell_type == "disasm":
            bookmarks[row].disasm = item.text()
        elif cell_type == "comment":
            bookmarks[row].comment = item.text()
        else:
            print_debug("Unknown field edited in bookmark table...")

    def open_trace(self, filename):
        """Opens and reads a trace file"""
        print_debug("Opening trace file: %s" % filename)
        self.close_trace()
        self.trace_data = trace_files.open_trace(filename)
        if self.trace_data is None:
            print_debug("Error, couldn't open trace file: %s" % filename)
        self.update_ui()
        self.update_column_widths(self.trace_table)

    def close_trace(self):
        """Clears trace and updates UI"""
        self.trace_data = None
        self.filtered_trace = None
        self.update_ui()

    def update_ui(self):
        """Updates tables and status bar"""
        self.update_trace_table()
        self.update_bookmark_table()
        self.update_status_bar()

    def save_trace(self):
        """Saves a trace file"""
        filename = self.trace_data.filename
        print_debug("Save trace: " + filename)
        if filename:
            trace_files.save_as_tv_trace(self.trace_data, filename)

    def show_about_dialog(self):
        """Shows an about dialog"""
        title = "About"
        name = prefs.PACKAGE_NAME
        version = prefs.PACKAGE_VERSION
        copyrights = prefs.PACKAGE_COPYRIGHTS
        url = prefs.PACKAGE_URL
        text = "%s %s \n %s \n %s" % (name, version, copyrights, url)
        QtWidgets.QMessageBox().about(self, title, text)

    def add_bookmark_to_table(self, bookmark):
        """Adds a bookmark to bookmark table"""
        table = self.bookmark_table
        row_count = table.rowCount()
        table.setRowCount(row_count + 1)

        startrow = QtWidgets.QTableWidgetItem(bookmark.startrow)
        startrow.setData(QtCore.Qt.DisplayRole, int(bookmark.startrow))
        startrow.setWhatsThis("startrow")
        table.setItem(row_count, 0, startrow)

        endrow = QtWidgets.QTableWidgetItem(bookmark.endrow)
        endrow.setData(QtCore.Qt.DisplayRole, int(bookmark.endrow))
        endrow.setWhatsThis("endrow")
        table.setItem(row_count, 1, endrow)

        address = QtWidgets.QTableWidgetItem(bookmark.addr)
        address.setWhatsThis("address")
        table.setItem(row_count, 2, address)

        disasm = QtWidgets.QTableWidgetItem(bookmark.disasm)
        disasm.setWhatsThis("disasm")
        table.setItem(row_count, 3, disasm)

        comment = QtWidgets.QTableWidgetItem(bookmark.comment)
        comment.setWhatsThis("comment")
        table.setItem(row_count, 4, comment)

    def update_column_widths(self, table):
        """Updates column widths of a TableWidget to match the content"""
        table.setVisible(False)  # fix ui glitch with column widths
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        table.setVisible(True)

    def update_trace_table(self):
        """Updates trace table"""
        table = self.trace_table

        if self.trace_data is None:
            table.setRowCount(0)
            return
        try:
            table.itemChanged.disconnect()
        except Exception:
            pass

        trace = self.get_visible_trace()
        row_count = len(trace)
        print_debug("Updating trace table: %d rows." % row_count)
        table.setRowCount(row_count)
        if row_count == 0:
            return

        ip_name = self.trace_data.get_instruction_pointer_name()
        if ip_name:
            ip_reg_index = self.trace_data.regs[ip_name]

        for i in range(0, row_count):
            row_id = str(trace[i]["id"])
            if ip_name:
                address = trace[i]["regs"][ip_reg_index]
                table.setItem(i, 1, QtWidgets.QTableWidgetItem(hex(address)))
            opcodes = trace[i]["opcodes"]
            disasm = trace[i]["disasm"]
            comment = str(trace[i]["comment"])
            comment_item = QtWidgets.QTableWidgetItem(comment)
            comment_item.setWhatsThis("comment")
            table.setItem(i, 0, QtWidgets.QTableWidgetItem(row_id))
            table.setItem(i, 2, QtWidgets.QTableWidgetItem(opcodes))
            table.setItem(i, 3, QtWidgets.QTableWidgetItem(disasm))
            table.setItem(i, 4, comment_item)
        table.itemChanged.connect(self.on_trace_table_cell_edited)

    def update_regs_and_mem(self):
        """Updates register and memory tables"""
        self.regs_list.clear()
        self.mem_list.clear()

        if self.trace_data is None:
            return

        table = self.trace_table
        row_ids = self.get_selected_row_ids(table)
        if not row_ids:
            return
        row_id = int(row_ids[0])
        trace_row = self.trace_data.trace[row_id]

        if "regs" in trace_row:
            reg_values = trace_row["regs"]
            for reg, reg_index in self.trace_data.regs.items():
                if (self.trace_data.arch in ('x86', 'x64') and prefs.REG_FILTER_ENABLED
                        and reg not in prefs.REG_FILTER):
                    continue  # don't show this register
                self.regs_list.addItem("%s: %s" % (reg, hex(reg_values[reg_index])))

            if "eflags" in self.trace_data.regs:
                eflags_index = self.trace_data.regs['eflags']
                eflags = reg_values[eflags_index]
                flags = {
                    "carry": eflags & 1,
                    "parity": (eflags >> 2) & 1,
                    # 'aux_carry': (eflags >> 4) & 1,
                    "zero": (eflags >> 6) & 1,
                    "sign": (eflags >> 7) & 1,
                    # 'direction': (eflags >> 10) & 1,
                    # 'overflow':  (eflags >> 11) & 1
                }
                eflags_bits = bin(eflags)
                self.regs_list.addItem("")
                self.regs_list.addItem("Eflags: %s = %s" % (hex(eflags), eflags_bits))

                self.regs_list.addItem(
                    "C:%s P:%s Z:%s S:%s"
                    % (flags["carry"], flags["parity"], flags["zero"], flags["sign"])
                )
        else:
            print_debug("Error. Could not get regs from row " + str(row_id))

        if "mem" in trace_row:
            mems = trace_row["mem"]
            for mem in mems:
                mem_str = ""
                for key, value in mem.items():
                    if isinstance(value, int):
                        value = hex(value)
                    mem_str += str(key) + ": " + str(value) + " "
                self.mem_list.addItem(mem_str)

    def update_status_bar(self):
        """Updates status bar"""
        if self.trace_data is None:
            return
        table = self.trace_table
        row = table.currentRow()

        row_count = table.rowCount()
        row_info = "%d/%d" % (row, row_count - 1)
        filename = self.trace_data.filename.split("/")[-1]
        msg = "File: %s | Row: %s " % (filename, row_info)

        selected_row_id = 0
        row_ids = self.get_selected_row_ids(table)
        if row_ids:
            selected_row_id = int(row_ids[0])

        bookmark = self.trace_data.get_bookmark_from_row(selected_row_id)
        if bookmark:
            msg += " | Bookmark: %s   ; %s" % (bookmark.disasm, bookmark.comment)
        self.status_bar.showMessage(msg)

    def get_selected_row_ids(self, table):
        """Returns IDs of all selected rows of TableWidget.

        Args:
            table: PyQt TableWidget
        returns:
            Ordered list of row ids
        """
        row_ids_set = set(
            table.item(index.row(), 0).text() for index in table.selectedIndexes()
        )
        row_ids_list = list(row_ids_set)
        try:
            row_ids_list.sort(key=int)
        except ValueError:
            print_debug("Error. Values in the first column must be integers.")
            return None
        return row_ids_list

    def trace_table_create_bookmark(self):
        """Context menu action for creating a bookmark"""
        table = self.trace_table
        selected = table.selectedItems()
        if not selected:
            print_debug("Could not create a bookmark. Nothing selected.")
            return
        first_row = selected[0].row()
        last_row = selected[-1].row()

        addr = table.item(first_row, 1).text()
        first_row_id = int(table.item(first_row, 0).text())
        last_row_id = int(table.item(last_row, 0).text())

        print_debug("New bookmark: %d-%d, addr: %s" % (first_row_id, last_row_id, addr))
        bookmark = Bookmark(startrow=first_row_id, endrow=last_row_id, addr=addr)
        self.trace_data.add_bookmark(bookmark)
        self.update_bookmark_table()

    def trace_table_print_cells(self):
        """Context menu action for trace table print cells"""
        items = self.trace_table.selectedItems()
        for item in items:
            self.print(item.text())

    def trace_table_context_menu_event(self):
        """Context menu for trace table right click"""
        self.trace_table_menu.popup(QtGui.QCursor.pos())

    def go_to_bookmark(self):
        """Goes to selected bookmark"""
        selected_row_ids = self.get_selected_row_ids(self.bookmark_table)
        if not selected_row_ids:
            print_debug("Error. No bookmark selected.")
            return
        row_id = int(selected_row_ids[0])
        if self.filter_check_box.isChecked():
            self.filter_check_box.setChecked(False)
        self.goto_row(self.trace_table, row_id)
        self.select_row(self.trace_table, row_id)
        self.tab_widget.setCurrentIndex(0)

    def clear_bookmarks(self):
        """Clears all bookmarks"""
        self.trace_data.clear_bookmarks()
        self.update_bookmark_table()

    def delete_bookmarks(self):
        """Deletes selected bookmarks"""
        selected = self.bookmark_table.selectedItems()
        if not selected:
            print_debug("Could not delete a bookmark. Nothing selected.")
            return
        selected_rows = sorted(set({sel.row() for sel in selected}))
        for row in reversed(selected_rows):
            self.trace_data.delete_bookmark(row)
        self.update_bookmark_table()

    def update_bookmark_table(self):
        """Updates bookmarks table from trace_data"""
        if self.trace_data is None:
            return
        table = self.bookmark_table
        try:
            table.itemChanged.disconnect()
        except Exception:
            pass
        table.setRowCount(0)
        bookmarks = self.trace_data.get_bookmarks()
        print_debug("Updating bookmark table: %d rows." % len(bookmarks))
        for bookmark in bookmarks:
            self.add_bookmark_to_table(bookmark)
        table.setSortingEnabled(True)
        table.itemChanged.connect(self.on_bookmark_table_cell_edited)
        self.update_column_widths(table)

    def on_trace_table_selection_changed(self):
        """Callback function for trace table selection change"""
        self.update_regs_and_mem()
        self.update_status_bar()

    def on_reg_list_selection_changed(self, item):
        """Prints the selected item on regList selection change"""
        if item is not None and prefs.PRINT_REG_ON_CLICK:
            self.print(item.text())

    def on_mem_list_selection_changed(self, item):
        """Prints the selected item on memList selection change"""
        if item is not None and prefs.PRINT_MEM_ON_CLICK:
            self.print(item.text())

    def print(self, text):
        """Prints text to TextEdit on log tab"""
        self.log_text_edit.appendPlainText(str(text))

    def goto_row(self, table, row):
        """Scrolls a table to the specified row"""
        table.scrollToItem(table.item(row, 3), QtWidgets.QAbstractItemView.PositionAtCenter)


    def select_row(self, table, row):
        """Selects a row in a table"""
        table.clearSelection()
        item = table.item(row, 0)
        table.setCurrentItem(
            item,
            QtCore.QItemSelectionModel.Select
            | QtCore.QItemSelectionModel.Rows
            | QtCore.QItemSelectionModel.Current,
        )

    def ask_user(self, title, question):
        """Shows a messagebox with yes/no question"""
        answer = QtWidgets.QMessageBox.question(
            self,
            title,
            question,
            QtWidgets.QMessageBox.StandardButtons(
                QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No
            )
        )
        return bool(answer == QtWidgets.QMessageBox.Yes)

    def show_messagebox(self, text):
        """Shows a messagebox"""
        alert = QtWidgets.QMessageBox()
        alert.setText(text)
        alert.exec_()


def print_debug(msg):
    """Prints a debug message"""
    if prefs.DEBUG:
        print(msg)
