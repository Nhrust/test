// zen-module — gtklock module: network and battery status, failed-login highlight.

#include "gtklock-module.h"

const gchar module_name[] = "zen";
#ifndef ZEN_MAJOR
#define ZEN_MAJOR 5
#endif
#ifndef ZEN_MINOR
#define ZEN_MINOR 0
#endif
const guint module_major_version = ZEN_MAJOR;
const guint module_minor_version = ZEN_MINOR;

static gchar *find_battery(void) {
	GDir *dir = g_dir_open("/sys/class/power_supply", 0, NULL);
	if(dir == NULL) return NULL;
	gchar *found = NULL;
	const gchar *name;
	while(found == NULL && (name = g_dir_read_name(dir)) != NULL) {
		gchar *type_path = g_build_filename("/sys/class/power_supply", name, "type", NULL);
		gchar *type = NULL;
		if(g_file_get_contents(type_path, &type, NULL, NULL) && g_str_has_prefix(type, "Battery"))
			found = g_build_filename("/sys/class/power_supply", name, NULL);
		g_free(type);
		g_free(type_path);
	}
	g_dir_close(dir);
	return found;
}

static gchar *read_line(const gchar *path) {
	gchar *text = NULL;
	if(!g_file_get_contents(path, &text, NULL, NULL)) return NULL;
	return g_strstrip(text);
}

static const gchar *network_state(void) {
	gchar *out = NULL;
	if(!g_spawn_command_line_sync("nmcli -t -f TYPE,STATE device", &out, NULL, NULL, NULL) || out == NULL)
		return "Offline";
	gboolean lan = FALSE, wifi = FALSE;
	gchar **lines = g_strsplit(out, "\n", -1);
	for(gchar **l = lines; *l != NULL; l++) {
		if(g_str_has_prefix(*l, "ethernet:connected")) lan = TRUE;
		if(g_str_has_prefix(*l, "wifi:connected")) wifi = TRUE;
	}
	g_strfreev(lines);
	g_free(out);
	if(lan && wifi) return "LAN+WIFI";
	if(lan) return "LAN";
	if(wifi) return "WIFI";
	return "Offline";
}

static gboolean update_status(gpointer data) {
	GtkLabel *label = GTK_LABEL(data);
	gchar *battery = find_battery();
	gchar *capacity = NULL, *status = NULL;
	if(battery != NULL) {
		gchar *path = g_build_filename(battery, "capacity", NULL);
		capacity = read_line(path);
		g_free(path);
		path = g_build_filename(battery, "status", NULL);
		status = read_line(path);
		g_free(path);
		g_free(battery);
	}
	gchar *text;
	if(capacity != NULL)
		text = g_strdup_printf("%s | BAT %s%%%s", network_state(), capacity,
			g_strcmp0(status, "Charging") == 0 ? "+" : "");
	else
		text = g_strdup_printf("%s", network_state());
	gtk_label_set_text(label, text);
	g_free(text);
	g_free(capacity);
	g_free(status);
	return G_SOURCE_CONTINUE;
}

static void status_destroyed(GtkWidget *label, gpointer data) {
	(void)label;
	g_source_remove(GPOINTER_TO_UINT(data));
}

static void error_label_changed(GObject *label, GParamSpec *pspec, gpointer data) {
	(void)pspec;
	const gchar *text = gtk_label_get_text(GTK_LABEL(label));
	GtkStyleContext *ctx = gtk_widget_get_style_context(GTK_WIDGET(data));
	if(text != NULL && text[0] != '\0') gtk_style_context_add_class(ctx, "failed");
	else gtk_style_context_remove_class(ctx, "failed");
}

static void input_changed(GtkEditable *field, gpointer data) {
	(void)data;
	if(gtk_entry_get_text_length(GTK_ENTRY(field)) > 0)
		gtk_style_context_remove_class(gtk_widget_get_style_context(GTK_WIDGET(field)), "failed");
}

void on_window_create(struct GtkLock *gtklock, struct Window *win) {
	(void)gtklock;

	GtkOverlay *overlay = GTK_OVERLAY(win->overlay);

	GtkWidget *status = gtk_label_new(NULL);
	gtk_widget_set_name(status, "zen-status");
	gtk_widget_set_halign(status, GTK_ALIGN_END);
	gtk_widget_set_valign(status, GTK_ALIGN_START);
	gtk_overlay_add_overlay(overlay, status);
	update_status(status);
	guint source = g_timeout_add_seconds(5, update_status, status);
	g_signal_connect(status, "destroy", G_CALLBACK(status_destroyed), GUINT_TO_POINTER(source));
	gtk_widget_show(status);

	g_signal_connect(win->error_label, "notify::label", G_CALLBACK(error_label_changed), win->input_field);
	g_signal_connect(win->input_field, "changed", G_CALLBACK(input_changed), NULL);
}
