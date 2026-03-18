/**
 * Im Mesh Client - Initialization
 * Global error handlers and client instantiation.
 */

// Global fallback for setConnectionType before client is initialized
function setConnectionType(type) {
    const tcpFields = document.getElementById('tcpFields');
    const serialFields = document.getElementById('serialFields');
    const tcpBtn = document.getElementById('connTypeTcp');
    const serialBtn = document.getElementById('connTypeSerial');

    if (type === 'serial') {
        if (tcpFields) tcpFields.style.display = 'none';
        if (serialFields) serialFields.style.display = 'block';
        if (tcpBtn) tcpBtn.classList.remove('conn-type-active');
        if (serialBtn) serialBtn.classList.add('conn-type-active');
    } else {
        if (tcpFields) tcpFields.style.display = 'block';
        if (serialFields) serialFields.style.display = 'none';
        if (tcpBtn) tcpBtn.classList.add('conn-type-active');
        if (serialBtn) serialBtn.classList.remove('conn-type-active');
    }
}

// Global error handler
window.addEventListener('error', function(e) {
    console.error('Global error:', e.error);
    console.error('Error at:', e.filename + ':' + e.lineno + ':' + e.colno);
});

window.addEventListener('unhandledrejection', function(e) {
    console.error('Unhandled promise rejection:', e.reason);
});

// Initialize when ready
const meshtasticClient = new MeshtasticClient();
window.meshtasticClient = meshtasticClient;

