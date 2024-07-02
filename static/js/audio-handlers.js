const AudioHandler = (function() {
    let isProcessing = false;

    function getAudioSettings() {
        return {
            targetLufs: document.getElementById('targetLufs').value,
            intensity: document.getElementById('processingIntensity').value,
            preserveQuiet: document.getElementById('preserveQuietParts').checked
        };
    }

    function processAudio() {
        console.log("processAudio function called");
        if (typeof VideoHandler === 'undefined' || typeof VideoHandler.getAllVideos !== 'function') {
            console.error("getAllVideos is not a function. Type:", typeof VideoHandler?.getAllVideos);
            return;
        }
        const videos = VideoHandler.getAllVideos();
        console.log("Videos:", videos);

        if (isProcessing) {
            alert('処理中です。しばらくお待ちください。');
            return;
        }

        isProcessing = true;
        updateUIStatus('音声処理を開始します...');

        const settings = getAudioSettings();

        if (videos.length === 0) {
            updateUIStatus('動画が見つかりません。先に動画をアップロードしてください。');
            isProcessing = false;
            return;
        }

        fetch('/process_audio', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                videos: videos,
                settings: settings
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                updateUIStatus('音声処理が完了しました');
                console.log('Audio processing completed successfully.');
                VideoHandler.updateVideoList(); // ビデオリストを更新
            } else {
                throw new Error(data.error || 'Unknown error occurred');
            }
        })
        .catch(error => {
            updateUIStatus('音声処理中にエラーが発生しました: ' + error.message);
            console.error('Error processing audio:', error);
        })
        .finally(() => {
            isProcessing = false;
        });
    }

    function previewAudioProcessing() {
        const settings = getAudioSettings();
        updateUIStatus('オーディオプレビューを生成中...');

        fetch('/preview_audio_processing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                const audioPreview = document.getElementById('audioPreview');
                audioPreview.src = data.previewUrl;
                audioPreview.style.display = 'block';
                audioPreview.play();
                updateUIStatus('オーディオプレビューの準備完了');
            } else {
                throw new Error(data.error || 'Unknown error occurred');
            }
        })
        .catch(error => {
            updateUIStatus('オーディオプレビューの生成中にエラーが発生しました: ' + error.message);
            console.error('Error previewing audio:', error);
        });
    }

    function updateUIStatus(message) {
        const statusElement = document.getElementById('audioProcessingStatus');
        if (statusElement) {
            statusElement.textContent = message;
        } else {
            console.log('Status update:', message);
        }
    }

    function updateAudioPreview() {
        console.log("Audio preview updated");
    }

    return {
        processAudio: processAudio,
        previewAudioProcessing: previewAudioProcessing,
        updateAudioPreview: updateAudioPreview
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    const processAudioButton = document.getElementById('processAudioButton');
    const previewAudioButton = document.getElementById('previewAudioButton');

    if (processAudioButton) {
        processAudioButton.addEventListener('click', AudioHandler.processAudio);
    }
    if (previewAudioButton) {
        previewAudioButton.addEventListener('click', AudioHandler.previewAudioProcessing);
    }
});