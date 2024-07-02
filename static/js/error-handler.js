window.ErrorHandler = {
    handleFetchErrors: function(response) {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}, statusText: ${response.statusText}`);
        }
        return response.json();
    },
    showError: function(message) {
        console.error('Error:', message);
        alert('Error: ' + message);
    }
};