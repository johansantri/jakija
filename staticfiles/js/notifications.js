// static/js/notifications.js
let notificationSocket = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

function connectWebSocket() {
    if (notificationSocket && 
        (notificationSocket.readyState === WebSocket.OPEN || 
         notificationSocket.readyState === WebSocket.CONNECTING)) {
        console.log("WebSocket sudah connect atau connecting, skip...");
        return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = protocol + '//' + window.location.host + '/ws/notifications/';

    notificationSocket = new WebSocket(wsUrl);

    notificationSocket.onopen = () => {
        console.log('WebSocket berhasil connect!');
        reconnectAttempts = 0;
        // Optional: request unread count lagi kalau perlu
    };

    notificationSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Pesan diterima:', data);

        if (data.type === 'unread_count') {
            updateBellBadge(data.count);
        } else if (data.type === 'notification') {
            showNotificationToast(data);
            incrementBellBadge();
        }
    };

    notificationSocket.onclose = (event) => {
        console.log('WebSocket ditutup. Code:', event.code, 'Reason:', event.reason);
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
            console.log(`Reconnect dalam ${delay/1000} detik... (attempt ${reconnectAttempts})`);
            setTimeout(connectWebSocket, delay);
        }
    };

    notificationSocket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

// Fungsi helper (sesuaikan dengan UI-mu)
function updateBellBadge(count) {
    const badge = document.getElementById('notif-count');
    if (badge) {
        badge.textContent = count > 0 ? count : '';
        badge.style.display = count > 0 ? 'inline' : 'none';
    }
}

function incrementBellBadge() {
    const badge = document.getElementById('notif-count');
    if (badge) {
        let current = parseInt(badge.textContent || '0', 10);
        badge.textContent = current + 1;
        badge.style.display = 'inline';
    }
}

function showNotificationToast(data) {
    // Implementasi toast/notifikasi popup
    // Contoh sederhana:
    alert(`Notifikasi baru: ${data.message}`);
    // Atau pakai library seperti Toastify, SweetAlert, dll.
}

// Jalankan sekali saat halaman load
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
});
