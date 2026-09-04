const functions = require("firebase-functions");
const admin = require("firebase-admin");

admin.initializeApp();

const RECIPIENT = "support@aviasafesystems.com";

function getTransporter() {
  var nodemailer = require("nodemailer");
  return nodemailer.createTransport({
    host: "smtp.gmail.com",
    port: 587,
    secure: false,
    auth: {
      user: functions.config().email?.user || "support@aviasafesystems.com",
      pass: functions.config().email?.password || "",
    },
  });
}

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

  var body = req.body || {};
  var contact_person = body.contact_person;
  var organization = body.organization;
  var work_email = body.work_email;
  var anti_bot = body.anti_bot;

  if (anti_bot) {
    res.redirect(302, "/?demo_requested=success");
    return;
  }

  if (!contact_person || !work_email) {
    res.status(400).send("Missing required fields");
    return;
  }

  try {
    var transporter = getTransporter();
    await transporter.sendMail({
      from: '"AviaSafe Demo" <' + (functions.config().email?.user || "support@aviasafesystems.com") + ">",
      to: RECIPIENT,
      replyTo: work_email,
      subject: "Demo Request: " + (organization || "Unknown") + " - " + contact_person,
      html: "<h2>New Demo Request</h2><hr>" +
        "<p><strong>Contact:</strong> " + contact_person + "</p>" +
        "<p><strong>Organization:</strong> " + (organization || "Not provided") + "</p>" +
        "<p><strong>Email:</strong> " + work_email + "</p>" +
        "<hr><p><strong>Date:</strong> " + new Date().toISOString() + "</p>" +
        "<p><strong>User Agent:</strong> " + (req.headers["user-agent"] || "Unknown") + "</p>",
    });

    admin.firestore().collection("demo_requests").add({
      contact_person: contact_person,
      organization: organization,
      work_email: work_email,
      date: new Date(),
      ip: req.ip,
    }).catch(function () {});

    res.redirect(302, "/?demo_requested=success");
  } catch (error) {
    console.error("Demo request error:", error);
    res.redirect(302, "/?demo_requested=success");
  }
});

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

  var body = req.body || {};
  var email = body.email;
  var tenant = body.tenant;
  var rating = body.rating;
  var subject = body.subject;
  var message = body.message;
  var page = body.page;
  var date = body.date;

  if (!message) {
    res.status(400).json({ error: "Message is required" });
    return;
  }

  var stars = rating && rating > 0 ? "\u2B50".repeat(Math.min(rating, 5)) : "Not rated";

  try {
    var transporter = getTransporter();
    await transporter.sendMail({
      from: '"AviaSafe Feedback" <' + (functions.config().email?.user || "support@aviasafesystems.com") + ">",
      to: RECIPIENT,
      replyTo: email && email !== "Anonymous" ? email : undefined,
      subject: "Feedback: " + (subject || "No subject"),
      html: "<h2>New Feedback from AviaSafe</h2><hr>" +
        "<p><strong>From:</strong> " + (email || "Anonymous") + "</p>" +
        "<p><strong>Tenant:</strong> " + (tenant || "Unknown") + "</p>" +
        "<p><strong>Rating:</strong> " + stars + "</p>" +
        "<p><strong>Subject:</strong> " + (subject || "No subject") + "</p>" +
        "<p><strong>Message:</strong></p>" +
        '<div style="background:#f5f7fa;padding:12px;border-radius:4px;">' + message + "</div>" +
        "<hr>" +
        "<p><strong>Page:</strong> " + (page || "Unknown") + "</p>" +
        "<p><strong>Date:</strong> " + (date || new Date().toISOString()) + "</p>" +
        "<p><strong>User Agent:</strong> " + (req.headers["user-agent"] || "Unknown") + "</p>",
    });

    admin.firestore().collection("feedback").add({
      email: email,
      tenant: tenant,
      rating: rating || null,
      subject: subject,
      message: message,
      page: page,
      date: new Date(),
      userAgent: req.headers["user-agent"],
    }).catch(function () {});

    res.status(200).json({ success: true, message: "Feedback sent successfully!" });
  } catch (error) {
    console.error("Feedback error:", error);
    res.status(500).json({ error: "Failed to send feedback. Please try again." });
  }
});
