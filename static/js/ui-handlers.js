const UIHandler = (function() {
    function handleCombineVideos() {
        if (VideoHandler.getVideos().length < 1) {
            alert('動画を選択しアップロードしてください');
            return;
        }
        const outputFileName = prompt('Enter output file name:', 'combined_video.mov');
        if (!outputFileName) return;
    
        const splitOption = document.getElementById('splitOption').value;
        const resolutionOption = document.getElementById('resolutionOption').value;
    
        // メタデータソースの取得
        const metadataDateSelect = document.getElementById('metadataDateSelect');
        const customVideoSelect = document.getElementById('customVideoSelect');
        let metadataSource = metadataDateSelect.value;
        let customVideoFilename = metadataSource === 'custom' ? customVideoSelect.value : null;
    
        console.log('Selected metadata source for combining:', metadataSource);
        console.log('Custom video filename (if applicable):', customVideoFilename);
    
        const videosWithOverlay = VideoHandler.getVideos().map(video => ({
            filename: video.filename,
            overlay: video.overlay
        }));
    
        const requestBody = {
            input_files: videosWithOverlay,
            output_file: outputFileName,
            split_duration: splitOption,
            resolution: resolutionOption,
            metadata_source: metadataSource,
            custom_video_filename: customVideoFilename
        };
    
        console.log('Sending request to server:', JSON.stringify(requestBody));
    
        fetch('/combine_videos', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => Promise.reject(err));
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                const creationDate = new Date(data.creation_time).toLocaleString();
                if (data.split_files) {
                    alert(`Videos combined and split successfully.\nOutput files: ${data.split_files.join(', ')}\nCreation date set to: ${creationDate}`);
                } else {
                    alert(`Videos combined successfully.\nOutput file: ${data.output_file}\nCreation date set to: ${creationDate}`);
                }
            } else {
                throw new Error(data.error || 'Unknown error occurred');
            }
        })
        .catch(error => {
            console.error('Error combining videos:', error);
            ErrorHandler.showError('Error combining videos: ' + (error.message || 'Unknown error'));
        });
    }

    function handleAddIntroOutro() {
        const introOutroOptions = document.getElementById('introOutroOptions');
        if (introOutroOptions) {
            introOutroOptions.style.display = introOutroOptions.style.display === 'none' ? 'block' : 'none';
        }

        if (VideoHandler.getVideos().length < 3) {
            alert('Please upload at least three videos: intro, main video, and outro.');
            return;
        }
        const outputFileName = prompt('Enter output file name:', 'video_with_intro_outro.mov');
        if (!outputFileName) return;

        const introDuration = document.getElementById('introDuration').value;
        const outroDuration = document.getElementById('outroDuration').value;
        const fadeDuration = document.getElementById('fadeDuration').value;
        const introText = document.getElementById('introText').value;
        const outroText = document.getElementById('outroText').value;

        fetch('/add_intro_outro', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                intro_video: VideoHandler.getVideos()[0].filename,
                main_video: VideoHandler.getVideos()[1].filename,
                outro_video: VideoHandler.getVideos()[2].filename,
                output_file: outputFileName,
                intro_duration: introDuration,
                outro_duration: outroDuration,
                fade_duration: fadeDuration,
                intro_text: introText,
                outro_text: outroText
            })
        })
        .then(ErrorHandler.handleFetchErrors)
        .then(data => {
            if (data.success) {
                alert(`Intro and outro added successfully. Output file: ${data.output_file}`);
            } else {
                throw new Error(data.error || 'Unknown error occurred');
            }
        })
        .catch(error => {
            ErrorHandler.showError('Error adding intro and outro: ' + error.message);
        });

        updateVideoSelectionDropdowns();
    }

    function updateVideoSelectionDropdowns() {
        const introSelect = document.getElementById('introVideoSelect');
        const mainSelect = document.getElementById('mainVideoSelect');
        const outroSelect = document.getElementById('outroVideoSelect');

        [introSelect, mainSelect, outroSelect].forEach(select => {
            if (select) {
                select.innerHTML = '';
                VideoHandler.getVideos().forEach(video => {
                    const option = document.createElement('option');
                    option.value = video.filename;
                    option.textContent = video.filename;
                    select.appendChild(option);
                });
            }
        });
    }

    function handlePreviewIntroOutro() {
        // ここにプレビュー機能の実装を追加
        alert('Preview functionality not implemented yet');
    }

    function initializeEventListeners() {
        const combineButton = document.getElementById('combineButton');
        if (combineButton) {
            combineButton.addEventListener('click', handleCombineVideos);
        }

        const addIntroOutroButton = document.getElementById('addIntroOutroButton');
        if (addIntroOutroButton) {
            addIntroOutroButton.addEventListener('click', handleAddIntroOutro);
        }

        const previewIntroOutroButton = document.getElementById('previewIntroOutro');
        if (previewIntroOutroButton) {
            previewIntroOutroButton.addEventListener('click', handlePreviewIntroOutro);
        }
    }

    return {
        handleCombineVideos: handleCombineVideos,
        handleAddIntroOutro: handleAddIntroOutro,
        updateVideoSelectionDropdowns: updateVideoSelectionDropdowns,
        initializeEventListeners: initializeEventListeners
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    UIHandler.initializeEventListeners();
});