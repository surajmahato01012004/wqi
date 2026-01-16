const USERS_KEY = "auth_users";
const LOGGED_IN_KEY = "auth_logged_in_email";

function loadUsers() {
    const raw = localStorage.getItem(USERS_KEY);
    if (!raw) return {};
    try {
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === "object" ? parsed : {};
    } catch (e) {
        return {};
    }
}

function saveUsers(users) {
    localStorage.setItem(USERS_KEY, JSON.stringify(users));
}

function validateEmailFormat(email) {
    const pattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return pattern.test(email);
}

function showMessage(element, message) {
    if (!element) return;
    if (!message) {
        element.classList.add("d-none");
        element.textContent = "";
    } else {
        element.textContent = message;
        element.classList.remove("d-none");
    }
}

async function hashPassword(password) {
    if (!window.crypto || !window.crypto.subtle) {
        return password;
    }
    const encoder = new TextEncoder();
    const data = encoder.encode(password);
    const hashBuffer = await window.crypto.subtle.digest("SHA-256", data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
}

document.addEventListener("DOMContentLoaded", function () {
    const loginForm = document.getElementById("loginForm");
    const signupForm = document.getElementById("signupForm");
    const logoutButton = document.getElementById("logoutButton");
    const emailDisplay = document.getElementById("userEmailDisplay");
    const loginError = document.getElementById("loginError");
    const signupError = document.getElementById("signupError");
    const signupSuccess = document.getElementById("signupSuccess");

    let users = loadUsers();
    const loggedInEmail = localStorage.getItem(LOGGED_IN_KEY);

    const path = window.location.pathname;
    const protectedPaths = ["/data", "/sensors", "/map", "/chatbot.html"];

    if (protectedPaths.includes(path)) {
        if (!loggedInEmail || !users[loggedInEmail]) {
            window.location.href = "/login";
            return;
        }
    }

    if (loginForm) {
        if (loggedInEmail && users[loggedInEmail]) {
            window.location.href = "/user-dashboard";
            return;
        }
        loginForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            showMessage(loginError, "");
            const emailInput = document.getElementById("loginEmail");
            const passwordInput = document.getElementById("loginPassword");
            const email = (emailInput.value || "").trim().toLowerCase();
            const password = passwordInput.value || "";
            if (!email || !password) {
                showMessage(loginError, "Please fill in all fields.");
                return;
            }
            if (!validateEmailFormat(email)) {
                showMessage(loginError, "Please enter a valid email address.");
                return;
            }
            if (password.length < 8) {
                showMessage(loginError, "Password must be at least 8 characters long.");
                return;
            }
            if (!users[email]) {
                showMessage(loginError, "Invalid email or password.");
                return;
            }
            const hashed = await hashPassword(password);
            if (users[email].passwordHash !== hashed) {
                showMessage(loginError, "Invalid email or password.");
                return;
            }
            localStorage.setItem(LOGGED_IN_KEY, email);
            window.location.href = "/user-dashboard";
        });
    }

    if (signupForm) {
        if (loggedInEmail && users[loggedInEmail]) {
            window.location.href = "/user-dashboard";
            return;
        }
        signupForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            showMessage(signupError, "");
            showMessage(signupSuccess, "");
            const emailInput = document.getElementById("signupEmail");
            const passwordInput = document.getElementById("signupPassword");
            const email = (emailInput.value || "").trim().toLowerCase();
            const password = passwordInput.value || "";
            if (!email || !password) {
                showMessage(signupError, "Please fill in all fields.");
                return;
            }
            if (!validateEmailFormat(email)) {
                showMessage(signupError, "Please enter a valid email address.");
                return;
            }
            if (password.length < 8) {
                showMessage(signupError, "Password must be at least 8 characters long.");
                return;
            }
            if (users[email]) {
                showMessage(signupError, "An account with this email already exists.");
                return;
            }
            const hashed = await hashPassword(password);
            users[email] = { passwordHash: hashed };
            saveUsers(users);
            localStorage.setItem(LOGGED_IN_KEY, email);
            showMessage(signupSuccess, "Account created successfully. Redirecting to dashboard...");
            setTimeout(function () {
                window.location.href = "/user-dashboard";
            }, 800);
        });
    }

    if (emailDisplay && logoutButton) {
        if (!loggedInEmail || !users[loggedInEmail]) {
            localStorage.removeItem(LOGGED_IN_KEY);
            window.location.href = "/login";
            return;
        }
        emailDisplay.textContent = loggedInEmail;
        logoutButton.addEventListener("click", function () {
            localStorage.removeItem(LOGGED_IN_KEY);
            window.location.href = "/login";
        });
    }
}
);
