/**
 * FOLDER/FILE PATH: public/dashboards/dashboard.js
 * VERSION NO: 1.0.0
 * DATE: 2026-07-17
 * PURPOSE OF THE FILE: Secures the airline manager dashboard, authenticates the 
 * user via Firebase Auth, retrieves isolated tenant data from Firestore, and 
 * calculates live Annex 19 safety pillar metrics.
 */

import { MASTER_QUESTIONS } from '../../survey/default_q.js';

// ── FIREBASE CONFIGURATION ──
const firebaseConfig = {
    apiKey: "AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc",
    authDomain: "aerosafety-sms-prod.firebaseapp.com",
    projectId: "aerosafety-sms-prod",
    storageBucket: "aerosafety-sms-prod.firebasestorage.app",
    messagingSenderId: "527947363983",
    appId: "1:527947363983:web:4b736b6d1d50dd9b7a22fa"
};

let db, auth;
let currentTenant = null;

// ── INITIALIZATION ──
document.addEventListener('DOMContentLoaded', async () => {
    try {
        // Dynamically import Firebase Auth and Firestore
        const { initializeApp } = await import("https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js");
        const { getAuth, signInWithEmailAndPassword, signOut, onAuthStateChanged } = await import("https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js");
        const { getFirestore, collection, getDocs, query, orderBy, limit } = await import("https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js");

        const app = initializeApp(firebaseConfig);
        auth = getAuth(app);
        db = getFirestore(app, "sms-db");

        bindEvents(signInWithEmailAndPassword, signOut);
        monitorAuthState(onAuthStateChanged, collection, getDocs, query, orderBy, limit);
    } catch (e) {
        console.error("Firebase SDK initialization failure: ", e);
    }
});

// ── EVENT BINDING ──
function bindEvents(signInWithEmailAndPassword, signOut) {
    const loginBtn = document.getElementById('loginBtn');
    const logoutBtn = document.getElementById('logoutBtn');

    loginBtn.addEventListener('click', async () => {
        const email = document.getElementById('emailInput').value.trim();
        const password = document.getElementById('passwordInput').value;
        const msg = document.getElementById('authMessage');
        
        msg.textContent = "Authenticating...";
        msg.style.color = "var(--navy)";

        try {
            await signInWithEmailAndPassword(auth, email, password);
        } catch (error) {
            msg.style.color = "var(--alert)";
            msg.textContent = "Authentication Failed. Please check your credentials.";
        }
    });

    logoutBtn.addEventListener('click', async () => {
        await signOut(auth);
        currentTenant = null;
        window.location.reload();
    });
}

// ── AUTHENTICATION STATE MONITOR ──
function monitorAuthState(onAuthStateChanged, collection, getDocs, query, orderBy, limit) {
    onAuthStateChanged(auth, (user) => {
        if (user) {
            // Map email domains to tenant IDs
            if (user.email.includes("sitaair")) currentTenant = "sita-air";
            else if (user.email.includes("taraair")) currentTenant = "tara-air";
            else currentTenant = "unknown";

            const heroUser = document.getElementById('dashHeroUser');
            if (heroUser) heroUser.textContent = user.email;

            loadDashboardUI();
            fetchTenantData(collection, getDocs, query, orderBy, limit);
        } else {
            document.getElementById('authSection').style.display = 'block';
            document.getElementById('dashboardSection').style.display = 'none';
            document.getElementById('logoutBtn').style.display = 'none';
        }
    });
}

function loadDashboardUI() {
    document.getElementById('authSection').style.display = 'none';
    document.getElementById('dashboardSection').style.display = 'block';
    document.getElementById('logoutBtn').style.display = 'block';
    document.getElementById('tenantTitle').textContent = `${currentTenant.toUpperCase()} - Safety Overview`;
}

// ── DATA FETCHING & CALCULATION ENGINE ──
async function fetchTenantData(collectionRef = null, getDocsRef = null, queryRef = null, orderByRef = null, limitRef = null) {
    if (!currentTenant) return;

    try {
        // Fallback for demo bypass if Firebase modules aren't passed via Auth state
        const { collection, getDocs, query, orderBy, limit } = await import("https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js");
        
        const q = query(collection(db, "tenants", currentTenant, "responses"), orderBy("submitted_at", "desc"), limit(50));
        const querySnapshot = await getDocs(q);
        
        const responses = [];
        querySnapshot.forEach((doc) => {
            responses.push(doc.data());
        });

        calculateMetrics(responses);
        populateTable(responses);

    } catch (error) {
        console.error("Error fetching tenant data: ", error);
        document.getElementById('tenantTitle').textContent += " (Data Access Error)";
    }
}

function calculateMetrics(responses) {
    if (responses.length === 0) return;

    // Map questions to pillars
    const pillars = {
        "Safety Policy & Objectives": { total: 0, max: 0 },
        "Safety Risk Management": { total: 0, max: 0 },
        "Safety Assurance": { total: 0, max: 0 },
        "Safety Promotion": { total: 0, max: 0 }
    };

    responses.forEach(response => {
        MASTER_QUESTIONS.forEach(q => {
            if (response[q.id] !== undefined && response[q.id] !== null) {
                let val = response[q.id];
                let score = 0;
                let maxPossible = 5;

                if (q.type === 'binary') {
                    score = val === true ? 5 : 0; // Aware = 5, Unaware = 0
                } else {
                    score = val; // Likert 1-5
                }

                pillars[q.pillar].total += score;
                pillars[q.pillar].max += maxPossible;
            }
        });
    });

    // Calculate percentages and update DOM
    const p1Score = pillars["Safety Policy & Objectives"].max > 0 ? Math.round((pillars["Safety Policy & Objectives"].total / pillars["Safety Policy & Objectives"].max) * 100) : 0;
    const p2Score = pillars["Safety Risk Management"].max > 0 ? Math.round((pillars["Safety Risk Management"].total / pillars["Safety Risk Management"].max) * 100) : 0;
    const p3Score = pillars["Safety Assurance"].max > 0 ? Math.round((pillars["Safety Assurance"].total / pillars["Safety Assurance"].max) * 100) : 0;
    const p4Score = pillars["Safety Promotion"].max > 0 ? Math.round((pillars["Safety Promotion"].total / pillars["Safety Promotion"].max) * 100) : 0;

    document.getElementById('scorePillar1').textContent = `${p1Score}%`;
    document.getElementById('scorePillar2').textContent = `${p2Score}%`;
    document.getElementById('scorePillar3').textContent = `${p3Score}%`;
    document.getElementById('scorePillar4').textContent = `${p4Score}%`;
}

function populateTable(responses) {
    const tbody = document.getElementById('dataBody');
    tbody.innerHTML = '';

    responses.forEach(res => {
        const dateObj = new Date(res.submitted_at);
        const formattedDate = dateObj.toLocaleDateString() + ' ' + dateObj.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${formattedDate}</td>
            <td>${res.department || 'Not Disclosed'}</td>
            <td>${res.years_experience || 'Not Disclosed'}</td>
            <td><span style="color: var(--success); font-weight: bold;">Processed</span></td>
        `;
        tbody.appendChild(row);
    });
}