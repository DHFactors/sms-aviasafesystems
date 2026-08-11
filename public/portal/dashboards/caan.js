/**
 * FOLDER/FILE PATH: public/dashboards/caan.js
 * VERSION NO: 1.0.0
 * DATE: 2026-07-17
 * PURPOSE OF THE FILE: Secures the CAAN SMD dashboard, authenticates the 
 * regulator via Firebase Auth, and aggregates the macro-level State Safety Programme data.
 */

// ── FIREBASE CONFIGURATION ──
const firebaseConfig = {
    apiKey: "AIzaSyCdCtUuyOcUIoCBEaiWGbhp6_XwZKHsicc",
    authDomain: "aerosafety-sms-prod.firebaseapp.com",
    projectId: "aerosafety-sms-prod",
    storageBucket: "aerosafety-sms-prod.firebasestorage.app",
    messagingSenderId: "527947363983",
    appId: "1:527947363983:web:4b736b6d1d50dd9b7a22fa"
};

// ── REAL AUTHENTICATION (Firebase Auth) ──
document.addEventListener('DOMContentLoaded', async () => {
    try {
        const { initializeApp } = await import("https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js");
        const { getAuth, signInWithEmailAndPassword, signOut, onAuthStateChanged } = await import("https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js");

        const app = initializeApp(firebaseConfig);
        const auth = getAuth(app);

        const loginBtn = document.getElementById('loginBtn');
        const logoutBtn = document.getElementById('logoutBtn');
        const msg = document.getElementById('authMessage');

        loginBtn.addEventListener('click', async () => {
            const email = document.getElementById('emailInput').value.trim();
            const password = document.getElementById('passwordInput').value;

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
            window.location.reload();
        });

        onAuthStateChanged(auth, (user) => {
            if (user) {
                const heroUser = document.getElementById('dashHeroUser');
                if (heroUser) heroUser.textContent = 'State Aviation Safety Oversight';
                loadDashboardUI();
                fetchAggregatedSSPData();
            } else {
                document.getElementById('authSection').style.display = 'block';
                document.getElementById('dashboardSection').style.display = 'none';
                document.getElementById('logoutBtn').style.display = 'none';
            }
        });
    } catch (e) {
        console.error("Firebase SDK initialization failure: ", e);
    }
});

function loadDashboardUI() {
    document.getElementById('authSection').style.display = 'none';
    document.getElementById('dashboardSection').style.display = 'block';
    document.getElementById('logoutBtn').style.display = 'block';
}

// ── MACRO DATA AGGREGATION ENGINE ──
function fetchAggregatedSSPData() {
    // In a fully deployed production environment, this function queries the 
    // "ssp_metrics" collection using the CAAN_AUDITOR role rules we set in firestore.rules.
    // For this deployment test phase, we render the architectural layout.
    
    const tbody = document.getElementById('sspBody');
    tbody.innerHTML = '';

    // Mock dataset representing live aggregation across the SSP
    const operators = [
        { name: "SITA AIR", p1: 82, p2: 76, p3: 88, p4: 71, count: 45 },
        { name: "TARA AIR", p1: 88, p2: 81, p3: 84, p4: 79, count: 62 },
        { name: "SUMMIT AIR", p1: 75, p2: 68, p3: 72, p4: 65, count: 28 },
        { name: "BUDDHA AIR", p1: 92, p2: 89, p3: 94, p4: 85, count: 110 }
    ];

    const getScoreClass = (score) => {
        if (score >= 85) return 'score-high';
        if (score >= 70) return 'score-mid';
        return 'score-low';
    };

    operators.forEach(op => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${op.name}</td>
            <td class="${getScoreClass(op.p1)}">${op.p1}%</td>
            <td class="${getScoreClass(op.p2)}">${op.p2}%</td>
            <td class="${getScoreClass(op.p3)}">${op.p3}%</td>
            <td class="${getScoreClass(op.p4)}">${op.p4}%</td>
            <td style="color: #64748B;">${op.count} reports</td>
        `;
        tbody.appendChild(row);
    });
}