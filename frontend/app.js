const API = {
    users: "/users",
    products: "/products",
    orders: "/orders"
};

let token = localStorage.getItem("cinema_token");
let selectedShow = null;
let selectedSeats = new Set();

async function api(url, options = {}) {
    const headers = {
        "Content-Type": "application/json",
        ...(options.headers || {})
    };

    if (token) {
        headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(url, {
        ...options,
        headers
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.detail || "Request failed");
    }

    return data;
}

function showLogin() {
    document.getElementById("auth-card").hidden = false;
    document.getElementById("name").hidden = true;
    document.getElementById("auth-title").textContent = "Login";
    document.getElementById("auth-submit").textContent = "Login";
}

function showRegister() {
    document.getElementById("auth-card").hidden = false;
    document.getElementById("name").hidden = false;
    document.getElementById("auth-title").textContent = "Register";
    document.getElementById("auth-submit").textContent = "Register";
}

document.getElementById("auth-form").addEventListener(
    "submit",
    async event => {
        event.preventDefault();

        const register =
            !document.getElementById("name").hidden;

        const body = {
            email: document.getElementById("email").value,
            password: document.getElementById("password").value
        };

        const endpoint = register ? "/users/register" : "/users/login";

        if (register) {
            body.name = document.getElementById("name").value;
        }

        try {
            const result = await api(endpoint, {
                method: "POST",
                body: JSON.stringify(body)
            });

            if (!register) {
                token = result.token;
                localStorage.setItem("cinema_token", token);
                document.getElementById("auth-message").textContent =
                    "Login successful!";
                updateAuthArea();
                loadBookings();
            } else {
                document.getElementById("auth-message").textContent =
                    "Registration successful. Please log in.";
                showLogin();
            }
        } catch (error) {
            document.getElementById("auth-message").textContent =
                error.message;
        }
    }
);

function updateAuthArea() {
    const area = document.getElementById("auth-area");

    if (token) {
        area.innerHTML = `
            <button onclick="logout()">Logout</button>
        `;
    } else {
        area.innerHTML = `
            <button onclick="showLogin()">Login</button>
            <button onclick="showRegister()">Register</button>
        `;
    }
}

function logout() {
    token = null;
    localStorage.removeItem("cinema_token");
    updateAuthArea();

    document.getElementById("booking-list").textContent =
        "Please log in to view your bookings.";
}

async function loadMovies() {
    const container = document.getElementById("movie-list");

    try {
        const movies = await api("/products/movies");

        if (!movies.length) {
            container.textContent = "No movies available.";
            return;
        }

        container.innerHTML = movies.map(movie => `
            <div class="movie-card">
                <img src="${escapeHTML(movie.poster_url || "")}"
                     alt="${escapeHTML(movie.title)}"
                     onerror="this.style.display='none'">
                <h3>${escapeHTML(movie.title)}</h3>
                <p>${escapeHTML(movie.language || "")}</p>
                <p>${escapeHTML(movie.description || "")}</p>
                <button onclick="loadShows(${movie.id})">
                    View Shows
                </button>
            </div>
        `).join("");
    } catch (error) {
        container.textContent = error.message;
    }
}

async function loadShows(movieId) {
    const container = document.getElementById("show-list");

    document.getElementById("show-section").hidden = false;
    document.getElementById("seat-section").hidden = true;

    try {
        const shows = await api(`/products/shows?movieId=${movieId}`);

        if (!shows.length) {
            container.textContent = "No upcoming shows available.";
            return;
        }

        container.innerHTML = shows.map(show => `
            <div class="show-card">
                <h3>${escapeHTML(show.title)}</h3>
                <p>Screen: ${escapeHTML(show.screen)}</p>
                <p>Time: ${new Date(show.starts_at).toLocaleString()}</p>
                <p>Price: ₹${show.price}</p>
                <button onclick="selectShow(${show.id})">
                    Select Seats
                </button>
            </div>
        `).join("");
    } catch (error) {
        container.textContent = error.message;
    }
}

async function selectShow(showId) {
    if (!token) {
        alert("Please log in before booking tickets.");
        showLogin();
        return;
    }

    try {
        selectedShow = await api(`/products/shows/${showId}`);
        selectedSeats.clear();

        document.getElementById("seat-section").hidden = false;
        renderSeats();
    } catch (error) {
        alert(error.message);
    }
}

function renderSeats() {
    const map = document.getElementById("seat-map");

    const rows = selectedShow.seat_rows;
    const columns = selectedShow.seats_per_row;
    const booked = selectedShow.booked_seats || [];

    map.innerHTML = "";

    for (let r = 1; r <= rows; r++) {
        for (let c = 1; c <= columns; c++) {
            const seat = String.fromCharCode(64 + r) + c;
            const button = document.createElement("button");

            button.className = "seat";
            button.textContent = seat;

            if (booked.includes(seat)) {
                button.classList.add("booked");
                button.disabled = true;
            } else {
                button.addEventListener("click", () => {
                    if (selectedSeats.has(seat)) {
                        selectedSeats.delete(seat);
                        button.classList.remove("selected");
                    } else {
                        selectedSeats.add(seat);
                        button.classList.add("selected");
                    }

                    updateTotal();
                });
            }

            map.appendChild(button);
        }
    }

    updateTotal();
}

function updateTotal() {
    const total = selectedSeats.size * selectedShow.price;

    document.getElementById("seat-total").textContent =
        `Selected: ${selectedSeats.size} seats | Total: ₹${total}`;
}

async function bookTickets() {
    if (!selectedShow || selectedSeats.size === 0) {
        alert("Please select at least one seat.");
        return;
    }

    try {
        const result = await api("/orders/", {
            method: "POST",
            body: JSON.stringify({
                showId: selectedShow.id,
                seats: [...selectedSeats]
            })
        });

        alert(
            `Booking confirmed!\nBooking ID: ${result.id}\n` +
            `Total: ₹${result.total}`
        );

        selectedSeats.clear();
        await selectShow(selectedShow.id);
        loadBookings();
    } catch (error) {
        alert(error.message);
        await selectShow(selectedShow.id);
    }
}

async function loadBookings() {
    if (!token) return;

    const container = document.getElementById("booking-list");

    try {
        const bookings = await api("/orders/");

        if (!bookings.length) {
            container.textContent = "No bookings found.";
            return;
        }

        container.innerHTML = bookings.map(order => `
            <div class="booking-card">
                <h3>${escapeHTML(order.movie_title)}</h3>
                <p>Booking ID: ${order.id}</p>
                <p>Seats: ${order.seats.map(escapeHTML).join(", ")}</p>
                <p>Total: ₹${order.total}</p>
                <p>Status: ${escapeHTML(order.status)}</p>
                ${
                    order.status === "CONFIRMED"
                    ? `<button onclick="cancelBooking(${order.id})">
                        Cancel Booking
                       </button>`
                    : ""
                }
            </div>
        `).join("");
    } catch (error) {
        container.textContent = error.message;
    }
}

async function cancelBooking(orderId) {
    if (!confirm("Are you sure you want to cancel this booking?")) {
        return;
    }

    try {
        await api(`/orders/${orderId}`, {
            method: "DELETE"
        });

        alert("Booking cancelled.");
        loadBookings();
    } catch (error) {
        alert(error.message);
    }
}

function escapeHTML(value) {
    return String(value).replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[char]);
}

updateAuthArea();
loadMovies();

if (token) {
    loadBookings();
}
