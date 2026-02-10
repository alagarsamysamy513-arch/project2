import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut, onAuthStateChanged, createUserWithEmailAndPassword, signInWithEmailAndPassword } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js";
import { getFirestore, doc, setDoc, getDoc } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore.js";

const firebaseConfig = {
  apiKey: "AIzaSyCvtizwlOpNOAuEQbZo0jMQQNR0PajuUhY",
  authDomain: "jeni-dc880.firebaseapp.com",
  projectId: "jeni-dc880",
  storageBucket: "jeni-dc880.firebasestorage.app",
  messagingSenderId: "172266584770",
  appId: "1:172266584770:web:f1964e7d83ecaa76edd95b",
  measurementId: "G-Q4J7ST4B3D"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

// Expose auth functions to window for use in HTML event handlers (since we are using modules)
window.auth = auth;
window.db = db;

// Handle Logout
window.handleLogout = async () => {
    try {
        await signOut(auth);
        // Also call backend logout to clear session
        window.location.href = '/logout';
    } catch (error) {
        console.error("Logout Error:", error);
    }
};

// Auth State Observer
onAuthStateChanged(auth, async (user) => {
    const loginBtn = document.getElementById('nav-login');
    const logoutBtn = document.getElementById('nav-logout');

    if (user) {
        if (loginBtn) loginBtn.classList.add('d-none');
        if (logoutBtn) logoutBtn.classList.remove('d-none');
        
        // Optionally: Sync session with backend if not already synced
        // fetch('/login', { method: 'POST', body: JSON.stringify({idToken: ...}) })
    } else {
        if (loginBtn) loginBtn.classList.remove('d-none');
        if (logoutBtn) logoutBtn.classList.add('d-none');
    }
});

export { auth, db, createUserWithEmailAndPassword, signInWithEmailAndPassword, doc, setDoc, getDoc };
