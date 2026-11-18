// Frappe's standard indicator colours; no custom colours.
frappe.listview_settings["NXERP Access Request"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colours = { Pending: "orange", Approved: "green", Rejected: "red", Cancelled: "gray" };
		return [__(doc.status), colours[doc.status] || "gray", "status,=," + doc.status];
	},
};
