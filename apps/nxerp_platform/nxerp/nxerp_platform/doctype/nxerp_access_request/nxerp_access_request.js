frappe.ui.form.on("NXERP Access Request", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Pending") return;
		for (const [label, decision] of [[__("Approve"), "Approve"], [__("Reject"), "Reject"]]) {
			frm.add_custom_button(label, () => {
				frappe.prompt(
					{ fieldname: "note", fieldtype: "Small Text", label: __("Note (optional)"), length: 500 },
					(values) => {
						frappe.call({
							method: "nxerp.api.access_request.decide",
							type: "POST",
							args: { name: frm.doc.name, decision, note: values.note || "" },
							freeze: true,
							callback: () => frm.reload_doc(),
						});
					},
					label,
				);
			}, __("Decision"));
		}
	},
});
