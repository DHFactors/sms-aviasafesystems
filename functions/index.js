const functions = require("firebase-functions");
const nodemailer = require("nodemailer");
const admin = require("firebase-admin");

admin.initializeApp();

// ============================================================
// Email transporter — configured via:
//   firebase functions:config:set email.user="..." email.password="..."
// For Gmail, use an App Password (not your login password).
// ============================================================
const transporter = nodemailer.createTransport({
  host: "smtp.gmail.com",
  port: 587,
  secure: false,
  auth: {
    user: functions.config().email?.user || "support@aviasafesystems.com",
    pass: functions.config().email?.password || "",
  },
});

const RECIPIENT = "support@aviasafesystems.com";

// ============================================================
// handleRequestDemo — POST form from index.html
// Receives: contact_person, organization, work_email, anti_bot
// Sends an email, then redirects to /?demo_requested=success
// ============================================================
exports.handleRequestDemo = functions.https.onRequest(async (req, res) => {
  res.set("Access-Control-Allow-Origin", "*");

  if (req.method === "OPTIONS") {
    res.set("Access-Control-Allow-Methods", "POST, OPTIONS");
    res.set("Access-Control-Allow-Headers", "Content-Type");
    res.status(204).send("");
    return;
  }

  if (req.method !== "POST") {
    res.status(405).send("Method not allowed");
    return;
  }

  const { contact_person, organization, work_email, anti_bot } = req.body;

  // Honeypot check — bots fill hidden fields
  if (anti_bot) {
    res.redirect(302, "/?demo_requested=success");
    return;
  }

  if (!contact_person || !work_email) {
    res.status(400).send("Missing required fields");
    return;
  }

  try {
    await transporter.sendMail({
      from: `"AviaSafe Demo" <${functions.config().email?.user || "support@aviasafesystems.com"}>`,
      to: RECIPIENT,
      replyTo: work_email,
      subject: `Demo Request: ${organization || "Unknown"} — ${contact_person}`,
      html: `
        <h2>New Demo Request</h2>
        <hr>
        <p><strong>Contact:</strong> ${contact_person}</p>
        <p><strong>Organization:</strong> ${organization || "Not provided"}</p>
        <p><strong>Email:</strong> ${work_email}</p>
        <hr>
        <p><strong>Date:</strong> ${new Date().toISOString()}</p>
        <p><strong>IP:</strong> ${req.ip || "Unknown"}</p>
        <p><strong>User Agent:</strong> ${req.headers["user-agent"] || "Unknown"}</p>
      `,
    });

    // Log to Firestore (optional, non-blocking)
    admin.firestore().collection("demo_requests").add({
      contact_person,
      organization,
      work_email,
      date: new Date(),
      ip: req.ip,
    }).catch(() => {});

    // Redirect to success page
    res.redirect(302, "/?demo_requested=success");
  } catch (error) {
    console.error("Demo request error:", error);
    res.redirect(302, "/?demo_requested=success");
  }
});

// ============================================================
// handleSendFeedback — POST JSON from feedback.js widget
// Receives: email, tenant, rating, subject, message, page, date
// Sends an email to support + logs to Firestore
// ============================================================
exports.handleSendFeedback = functions.https.onRequest(async (req, res) => {
  res.set("Access-Control-Allow-Origin", "*");
  res.set("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.set("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    res.status(204).send("");
    return;
  }

  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const { email, tenant, rating, subject, message, page, date } = req.body;

  if (!message) {
    res.status(400).json({ error: "Message is required" });
    return;
  }

  const stars = rating && rating > 0 ? "⭐".repeat(Math.min(rating, 5)) : "Not rated";

  try {
    await transporter.sendMail({
      from: `"AviaSafe Feedback" <${functions.config().email?.user || "support@aviasafesystems.com"}>`,
      to: RECIPIENT,
      replyTo: email && email !== "Anonymous" ? email : undefined,
      subject: `Feedback: ${subject || "No subject"}`,
      html: `
        <h2>New Feedback from AviaSafe</h2>
        <hr>
        <p><strong>From:</strong> ${email || "Anonymous"}</p>
        <p><strong>Tenant:</strong> ${tenant || "Unknown"}</p>
        <p><strong>Rating:</strong> ${stars}</p>
        <p><strong>Subject:</strong> ${subject || "No subject"}</p>
        <p><strong>Message:</strong></p>
        <div style="background:#f5f7fa;padding:12px;border-radius:4px;">${message}</div>
        <hr>
        <p><strong>Page:</strong> ${page || "Unknown"}</p>
        <p><strong>Date:</strong> ${date || new Date().toISOString()}</p>
        <p><strong>User Agent:</strong> ${req.headers["user-agent"] || "Unknown"}</p>
      `,
    });

    // Log to Firestore
    admin.firestore().collection("feedback").add({
      email,
      tenant,
      rating: rating || null,
      subject,
      message,
      page,
      date: new Date(),
      userAgent: req.headers["user-agent"],
    }).catch(() => {});

    res.status(200).json({ success: true, message: "Feedback sent successfully!" });
  } catch (error) {
    console.error("Feedback error:", error);
    res.status(500).json({ error: "Failed to send feedback. Please try again." });
  }
});
