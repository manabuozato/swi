// utils.js
const Utils = {
    formatDate: function(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString();
    },
    // 他のユーティリティ関数をここに追加
};

// グローバルスコープに追加
window.Utils = Utils;