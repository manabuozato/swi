const VideoHandler = (function() {
    console.log('video-handlers.js loaded');
    let videos = [];
    let originalOrder = []; // 元の順序を保持する配列
    let sortOrder = {
        upload: null,
        creation: null,
        size: null,
        duration: null
    };
    let totalDuration = 0;
    let currentPlayingVideo = null;
    let isCombining = false;
    let combineInProgress = false;
    let initialized = false;

    console.log('formatDate function:', typeof formatDate);

    // video-handlers.js の先頭付近に以下を追加
    window.formatDate = function(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString();
    };

    function formatDate(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString();
    }

    function loadVideoList(start, count) {
        fetch(`/get_videos?start=${start}&count=${count}`)
            .then(response => response.json())
            .then(data => {
                data.videos.forEach(video => {
                    const videoItem = createVideoItem(video);
                    document.getElementById('videoList').appendChild(videoItem);
                });
                if (data.hasMore) {
                    // 必要に応じて追加のビデオを読み込む
                    loadVideoList(start + count, count);
                }
            });
    }

    async function loadVideos() {
        console.log('Loading videos...');
        try {
            const response = await fetch('/get_videos');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            console.log('Received video data:', data);
            if (!Array.isArray(data.videos)) {
                console.error('Invalid data format: videos is not an array');
                return;
            }
            videos = data.videos.map(video => ({
                filename: video,
                creationTime: null,
                uploadTime: null,
                duration: 0,
                overlays: []
            }));
            originalOrder = [...videos]; // ここで originalOrder を初期化
            console.log('Processed video data:', videos);
            updateVideoList();
            updateCombineButton();
            await getVideoInfo();
            
            updateTotalDuration();
            
        } catch (error) {
            console.error('Error loading videos:', error);
            ErrorHandler.showError('Failed to load videos: ' + error.message);
        }
    }

    function loadVideo(filename, videoItem) {
        console.log('Loading video:', filename);
        console.log('Video item:', videoItem);
    
        if (!videoItem) {
            console.error('Video item not found');
            return;
        }
        const videoContainer = videoItem.querySelector('.video-preview-container');
        if (!videoContainer) {
            console.error('Video preview container not found');
            return;
        }
        videoContainer.innerHTML = `
            <video src="/uploads/${filename}" class="video-preview" controls style="max-width: 320px; width: 100%; height: auto;"></video>
        `;
    
        const videoElement = videoContainer.querySelector('video');
        if (videoElement) {
            videoElement.addEventListener('loadedmetadata', function() {
                console.log(`Video loaded successfully: ${filename}`);
            });
            videoElement.addEventListener('error', function(e) {
                console.error('Error loading video:', e);
                ErrorHandler.showError('Error loading video: ' + e.message);
            });
        }
    }
    

    function startVideoProcessing(inputFile, outputFile) {
        fetch('/start_processing', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                input_file: inputFile,
                output_file: outputFile
            })
        })
        .then(response => response.json())
        .then(data => {
            console.log(data.message);
            // ここでプログレス表示を開始
        });
    }


    function getAllVideos() {
        return videos.map(video => video.filename);
    }

    function updateVideoPreview(filename) {
        const videoElement = document.querySelector(`.video-item[data-filename="${filename}"] video`);
        if (videoElement) {
            fetch(`/video_metadata/${filename}`)
                .then(ErrorHandler.handleFetchErrors)
                .then(metadata => {
                    videoElement.src = `/uploads/${filename}`;
                    videoElement.load();
                    videoElement.onerror = function(e) {
                        console.error('Error loading video:', e);
                        const errorMessage = document.createElement('p');
                        errorMessage.textContent = 'ビデオの読み込みに失敗しました。再読み込みしてください。';
                        errorMessage.style.color = 'red';
                        videoElement.parentNode.insertBefore(errorMessage, videoElement.nextSibling);
                    };
                })
                .catch(error => {
                    console.error('Error fetching video metadata:', error);
                    ErrorHandler.showError('Error fetching video metadata: ' + error.message);
                });
        }
    }

    function getVideoInfo() {
        const promises = videos.map(video => 
            fetch(`/video_info/${video.filename}`)
                .then(ErrorHandler.handleFetchErrors)
                .then(data => {
                    video.creationTime = data.creation_time * 1000;  // ミリ秒に変換
                    video.uploadTime = data.upload_time * 1000;  // ミリ秒に変換
                    video.duration = data.duration;
                    video.size = data.size;
                    video.resolution = data.resolution;
                    console.log(`Video info for ${video.filename}:`, {
                        creationTime: new Date(video.creationTime),
                        uploadTime: new Date(video.uploadTime)
                    });
                    updateVideoTimes(video.filename, formatDate(video.creationTime), formatDate(video.uploadTime));
                })
                .catch(error => {
                    console.error(`Error fetching info for ${video.filename}:`, error);
                })
        );
    
        return Promise.all(promises);
            updateTotalDuration();  // ここに追加
    }

    function updateVideoTimes(filename, creationTime, uploadTime) {
        const videoItem = document.querySelector(`.video-item[data-filename="${filename}"]`);
        if (videoItem) {
            const creationTimeElement = videoItem.querySelector('.creation-time');
            const uploadTimeElement = videoItem.querySelector('.upload-time');
            if (creationTimeElement) {
                creationTimeElement.textContent = `Created: ${creationTime}`;
            }
            if (uploadTimeElement) {
                uploadTimeElement.textContent = `Uploaded: ${uploadTime}`;
            }
        }
    }
    function sortVideos(criteria) {
        console.log('Sorting videos by:', criteria);
        console.log('Current sort order:', sortOrder[criteria]);
        console.log('Before sort:', videos.map(v => ({filename: v.filename, creationTime: new Date(v.creationTime), uploadTime: new Date(v.uploadTime)})));
    
        // 現在の基準のソート順を更新
        if (sortOrder[criteria] === null || sortOrder[criteria] === 'desc') {
            sortOrder[criteria] = 'asc';
        } else {
            sortOrder[criteria] = 'desc';
        }
    
        // 他の基準のソート順をリセット
        Object.keys(sortOrder).forEach(key => {
            if (key !== criteria) sortOrder[key] = null;
        });
    
        videos.sort((a, b) => {
            let comparison = 0;
            switch(criteria) {
                case 'upload':
                    comparison = a.uploadTime - b.uploadTime;
                    break;
                case 'creation':
                    comparison = a.creationTime - b.creationTime;
                    break;
                case 'size':
                    comparison = a.size - b.size;
                    break;
                case 'duration':
                    comparison = a.duration - b.duration;
                    break;
            }
            
            return sortOrder[criteria] === 'asc' ? comparison : -comparison;
        });
    
        console.log('After sort:', videos.map(v => ({filename: v.filename, creationTime: new Date(v.creationTime), uploadTime: new Date(v.uploadTime)})));
        console.log('New sort order:', sortOrder[criteria]);
        updateVideoList();
        updateSortButtonText(criteria);
        loadVideoDetails(); // ここに追加: ソート後に詳細情報を再読み込み
    }

    function loadVideoDetails() {
        if (!videos || videos.length === 0) {
            console.log('No videos to load details for');
            return Promise.resolve();
        }
    
        const promises = videos.map(video => 
            fetch(`/video_info/${video.filename}`)
                .then(response => response.json())
                .then(data => {
                    Object.assign(video, data);
                    const videoItem = document.querySelector(`.video-item[data-filename="${video.filename}"]`);
                    if (videoItem) {
                        updateVideoDetails(videoItem, video);
                    }
                })
                .catch(error => {
                    console.error(`Error fetching info for ${video.filename}:`, error);
                })
        );
    
        return Promise.all(promises);
    }
    
    function updateSortButtonText(criteria) {
        const button = document.getElementById(`sortBy${criteria.charAt(0).toUpperCase() + criteria.slice(1)}`);
        if (button) {
            let text;
            if (criteria === 'creation') {
                text = '作成';
            } else if (criteria === 'upload') {
                text = 'アップロード順';
            } else if (criteria === 'size') {
                text = 'ファイル容量順';
            } else if (criteria === 'duration') {
                text = '動画時間';
            } else {
                text = `順 ${criteria}`;
            }
    
            if (sortOrder[criteria] === 'asc') {
                text += ' (昇順)';
            } else if (sortOrder[criteria] === 'desc') {
                text += ' (降順)';
            }
            button.textContent = text;
        }
    }

    function updateVideoList() {
        console.log('Updating video list with:', videos);
        const videoList = document.getElementById('videoList');
        if (!videoList) {
            console.error('Video list element not found');
            return;
        }
        
        // ソートボタンと入力フィールドを保持
        const sortButtons = document.querySelector('.sort-buttons');
        const fileUpload = document.querySelector('.file-upload');
        
        videoList.innerHTML = '';
        
        // ソートボタンと入力フィールドを再追加
        if (sortButtons) videoList.appendChild(sortButtons);
        if (fileUpload) videoList.appendChild(fileUpload);
    
        videos.forEach(video => {
            const videoItem = createVideoItem(video);
            videoList.appendChild(videoItem);
            updateVideoDetails(videoItem, video); // 既存の情報で更新
        });
    
        console.log('Updated video list:', videos.map(v => v.filename));
        updateCombineButton();
        updateTotalDuration();
        updateCurrentVideoDisplay();
    }

    function useOverlaidVideo(originalFilename, overlaidFilename) {
        fetch('/use_overlaid_video', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                original_filename: originalFilename,
                overlaid_filename: overlaidFilename
            })
        })
        .then(ErrorHandler.handleFetchErrors)
        .then(data => {
            if (data.success) {
                alert('Overlaid video will be used for combining.');
                updateVideoList();
            } else {
                throw new Error(data.error || 'Unknown error occurred');
            }
        })
        .catch(error => {
            ErrorHandler.showError('Error using overlaid video: ' + error.message);
        });
    }

    function createVideoItem(video) {
        const videoItem = document.createElement('div');
        videoItem.className = 'video-item';
        videoItem.setAttribute('data-filename', video.filename);
        videoItem.innerHTML = `
            <div class="video-left">
                <p class="video-filename">${video.filename}</p>
                <img src="/thumbnails/${video.filename}" class="video-thumbnail" alt="${video.filename}">
                <video src="/uploads/${video.filename}" class="video-preview"></video>
                <div class="video-controls">
                    <button class="btn btn-sm btn-info preview-btn">プレビュー</button>
                    <button class="btn btn-sm btn-danger delete-btn">削除</button>
                </div>
            </div>
            <div class="video-right">
                <p>長さ: <span class="video-duration"></span></p>
                <p>サイズ: <span class="video-size"></span> MB</p>
                <p>解像度: <span class="video-resolution"></span></p>
                <p class="creation-time"></p>
                <p class="upload-time"></p>
            </div>
        `;
        attachEventListeners(videoItem);
        return videoItem;
    }

    function updateOverlayList(videoItem, overlays) {
        const overlayList = videoItem.querySelector('.overlay-list');
        overlayList.innerHTML = '';
        overlays.forEach((overlay, index) => {
            const overlayItem = document.createElement('div');
            overlayItem.className = 'overlay-item';
            overlayItem.innerHTML = `
                <p>Overlay ${index + 1}: ${overlay.text}</p>
                <button class="btn btn-sm btn-danger remove-overlay-btn" data-index="${index}">Remove</button>
            `;
            overlayList.appendChild(overlayItem);
        });

        // オーバーレイ削除ボタンのイベントリスナー
        const removeButtons = overlayList.querySelectorAll('.remove-overlay-btn');
        removeButtons.forEach(button => {
            button.addEventListener('click', function() {
                const filename = videoItem.getAttribute('data-filename');
                const index = parseInt(this.getAttribute('data-index'));
                removeOverlay(filename, index);
            });
        });
    }

    function attachEventListeners(element) {
        const videoElement = element.querySelector('.video-preview');
        if (videoElement) {
            // 既存のビデオ関連のイベントリスナーをそのまま保持
            videoElement.addEventListener('play', function() {
                if (currentPlayingVideo && currentPlayingVideo !== this) {
                    currentPlayingVideo.pause();
                }
                currentPlayingVideo = this;
                updateVideoInfo(this);
            });
    
            videoElement.addEventListener('ended', function() {
                const nextVideo = this.closest('.video-item').nextElementSibling;
                if (nextVideo) {
                    const nextVideoElement = nextVideo.querySelector('video');
                    if (nextVideoElement) {
                        nextVideoElement.play();
                    }
                }
            });
    
            videoElement.addEventListener('error', function(e) {
                console.error('Video load error:', e);
                ErrorHandler.showError('Video load error: ' + e.message);
            });
    
            videoElement.addEventListener('loadedmetadata', function() {
                console.log(`Video loaded successfully: ${element.getAttribute('data-filename')}`);
            });
        }
    
        const previewBtn = element.querySelector('.preview-btn');
        if (previewBtn) {
            previewBtn.addEventListener('click', function() {
                const videoItem = this.closest('.video-item');
                const thumbnail = videoItem.querySelector('.video-thumbnail');
                const videoPreview = videoItem.querySelector('.video-preview');
                
                if (thumbnail && videoPreview) {
                    if (thumbnail.style.display !== 'none') {
                        thumbnail.style.display = 'none';
                        videoPreview.style.display = 'block';
                        videoPreview.play();
                        this.textContent = '画像に戻す';
                    } else {
                        thumbnail.style.display = 'block';
                        videoPreview.style.display = 'none';
                        videoPreview.pause();
                        this.textContent = 'プレビュー';
                    }
                } else {
                    console.error('Thumbnail or video preview element not found');
                }
            });
        }
    
        const deleteBtn = element.querySelector('.delete-btn');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', function() {
                const filename = this.closest('.video-item').getAttribute('data-filename');
                deleteVideo(filename, this.closest('.video-item'));
            });
        }
    
        // 既存のオーバーレイ関連のイベントリスナーをそのまま保持
        const addOverlayBtn = element.querySelector('.add-overlay-btn');
        if (addOverlayBtn) {
            addOverlayBtn.addEventListener('click', function() {
                const filename = this.getAttribute('data-filename');
                showOverlayModal(filename);
            });
        }
    
        const addTextBtn = element.querySelector('.add-text-btn');
        if (addTextBtn) {
            addTextBtn.addEventListener('click', function() {
                const filename = this.getAttribute('data-filename');
                showOverlayModal(filename);
            });
        }
    }


    
    function showOverlayModal(filename) {
        const modal = document.getElementById('textOverlayModal');
        const videoFilenameInput = document.getElementById('videoFilename');
        const modalTitle = modal.querySelector('h2');
        
        videoFilenameInput.value = filename;
        modalTitle.textContent = `${filename} にテキストを追加`;
        modal.style.display = 'block';
    
        // 既存のオーバーレイ情報があれば表示
        const existingOverlay = videos.find(v => v.filename === filename)?.overlay;
        if (existingOverlay) {
            document.getElementById('overlayText').value = existingOverlay.text;
            document.getElementById('overlayPosition').value = existingOverlay.position;
            document.getElementById('overlayColor').value = existingOverlay.color;
            document.getElementById('overlayFontSize').value = existingOverlay.font_size;
            document.getElementById('overlayDurationType').value = existingOverlay.duration === 'full' ? 'full' : 'custom';
            document.getElementById('overlayDurationSeconds').value = existingOverlay.duration === 'full' ? '' : existingOverlay.duration;
        } else {
            // フォームをリセット
            document.getElementById('overlayText').value = '';
            document.getElementById('overlayPosition').value = 'center';
            document.getElementById('overlayColor').value = '#ffffff';
            document.getElementById('overlayFontSize').value = '50';
            document.getElementById('overlayDurationType').value = 'full';
            document.getElementById('overlayDurationSeconds').value = '';
        }
    }

    function removeOverlay(filename, index) {
        const videoIndex = videos.findIndex(v => v.filename === filename);
        if (videoIndex !== -1 && videos[videoIndex].overlays) {
            videos[videoIndex].overlays.splice(index, 1);
            updateOverlayList(document.querySelector(`.video-item[data-filename="${filename}"]`), videos[videoIndex].overlays);
        }
    }

    function addTextOverlay() {
        console.log('テキストオーバーレイの追加を開始します');
        const videoFilename = document.getElementById('videoFilename').value;
        
        if (!videoFilename) {
            alert('最初に動画を選択してください');
            return;
        }

        const overlayText = document.getElementById('overlayText').value.trim();
        if (!overlayText) {
            alert('テキストを入力してください');
            return;
        }

        const overlayData = {
            video_filename: videoFilename,
            text: overlayText,
            position: document.getElementById('overlayPosition').value,
            color: document.getElementById('overlayColor').value,
            font_size: document.getElementById('overlayFontSize').value,
            duration: document.getElementById('overlayDurationType').value === 'full' ? 'full' : document.getElementById('overlayDurationSeconds').value || '5',
            padding: document.getElementById('overlayPadding').value || '10'
        };
    
        console.log('オーバーレイデータ:', overlayData);
    
        // サーバーにデータを送信
        fetch('/add_text_overlay', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(overlayData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('テキストオーバーレイが追加されました');
                document.getElementById('textOverlayModal').style.display = 'none';
                VideoHandler.loadVideos();  // ビデオリストを更新
            } else {
                throw new Error(data.error || '不明なエラーが発生しました');
            }
        })
        .catch(error => {
            console.error('エラー:', error);
            alert('テキストオーバーレイの追加中にエラーが発生しました: ' + error.message);
        });
    }

    
    
    // DOMContentLoadedイベントリスナー内に以下を追加
    document.getElementById('addOverlayBtn').addEventListener('click', addTextOverlay);

    function updateVideoInfo(videoElement) {
        const videoItem = videoElement.closest('.video-item');
        if (videoItem) {
            const filename = videoItem.getAttribute('data-filename');
            fetch(`/video_info/${filename}`)
                .then(response => response.json())
                .then(data => {
                    const durationElement = videoItem.querySelector('.video-duration');
                    if (durationElement) {
                        durationElement.textContent = `Duration: ${data.duration.toFixed(2)} seconds`;
                    }
                    // 他の情報も必要に応じて更新
                })
                .catch(error => console.error('Error updating video info:', error));
        }
    }

    function deleteVideo(filename, element) {
        if (!filename) {
            console.error('Filename is null or undefined');
            return;
        }
        fetch(`/delete/${filename}`, { method: 'POST' })
            .then(ErrorHandler.handleFetchErrors)
            .then(data => {
                if (data.success) {
                    element.remove();
                    videos = videos.filter(v => v.filename !== filename);
                    updateCombineButton();
                    updateTotalDuration();
                    updateVideoList();
                } else {
                    throw new Error(data.error || 'Unknown error occurred');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                ErrorHandler.showError('Error deleting video: ' + error.message);
            });
    }

    function updateCombineButton() {
        const combineButton = document.getElementById('combineButton');
        const uploadedCount = document.getElementById('uploadedVideoCount');
        if (uploadedCount) {
            uploadedCount.textContent = videos.length;
        }
        if (combineButton) {
            combineButton.disabled = videos.length === 0;
            combineButton.textContent = videos.length > 1 ? '結合する' : '実行する';
        }
    }

    function updateTotalDuration() {
        totalDuration = videos.reduce((total, video) => total + (video.duration || 0), 0);
        const totalDurationElement = document.getElementById('totalDuration');
        if (totalDurationElement) {
            totalDurationElement.textContent = formatDuration(totalDuration);
        }
    }

    function uploadFiles(files) {
        console.log('uploadFiles function called', files);
        return new Promise((resolve, reject) => {
            const formData = new FormData();
            Array.from(files).forEach((file, index) => {
                formData.append('file', file);
                const originalDate = file.lastModified ? new Date(file.lastModified) : new Date();
                formData.append(`original_creation_time_${index}`, originalDate.toISOString());
            });
    
            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/upload', true);
    
            // プログレスバーの表示
            const progressContainer = document.getElementById('uploadProgress');
            const progressBar = progressContainer.querySelector('.progress-bar');
            const uploadStatus = document.getElementById('uploadStatus');
            progressContainer.style.display = 'block';
    
            const startTime = Date.now();
    
            xhr.upload.onprogress = function(event) {
                if (event.lengthComputable) {
                    const percentComplete = (event.loaded / event.total) * 100;
                    const elapsedTime = (Date.now() - startTime) / 1000; // 秒単位
                    const uploadSpeed = event.loaded / elapsedTime; // バイト/秒
                    const remainingTime = (event.total - event.loaded) / uploadSpeed; // 秒単位
    
                    progressBar.style.width = percentComplete + '%';
                    progressBar.setAttribute('aria-valuenow', percentComplete);
                    progressBar.textContent = `${percentComplete.toFixed(2)}%`;
                    uploadStatus.textContent = `残り時間: ${formatTime(remainingTime)}`;
                }
            };
    
            xhr.onload = function() {
                if (xhr.status === 200) {
                    const data = JSON.parse(xhr.responseText);
                    console.log('Upload response:', data);
                    if (Array.isArray(data)) {
                        data.forEach(fileData => {
                            if (fileData.success) {
                                console.log('File uploaded successfully:', fileData.filename);
                                if (fileData.thumbnail) {
                                    console.log('Thumbnail created:', fileData.thumbnail);
                                }
                            } else {
                                console.error('Upload failed for file:', fileData.error);
                            }
                        });
                    } else {
                        console.error('Unexpected response format:', data);
                    }
                    loadVideos().then(() => {
                        loadVideoDetails();
                        resolve(data);
                    });
                } else {
                    console.error('Upload error:', xhr.statusText);
                    ErrorHandler.showError('Upload failed: ' + xhr.statusText);
                    reject(new Error(xhr.statusText));
                }
                progressContainer.style.display = 'none';
            };
    
            xhr.onerror = function() {
                console.error('Upload error:', xhr.statusText);
                ErrorHandler.showError('Upload failed: ' + xhr.statusText);
                progressContainer.style.display = 'none';
                reject(new Error(xhr.statusText));
            };
    
            xhr.send(formData);
        });
    }
    
    function formatTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = Math.round(seconds % 60);
        return `${minutes}分${remainingSeconds}秒`;
    }
    
    function formatTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = Math.round(seconds % 60);
        return `${minutes}分${remainingSeconds}秒`;
    }
    
    function updateVideoInfo(filename, info) {
        const videoItem = document.querySelector(`.video-item[data-filename="${filename}"]`);
        if (videoItem) {
            updateVideoDetails(videoItem, info);    
        }
    }

   

    function initializeEventListeners() {
        console.log('Initializing event listeners');
        const uploadButton = document.getElementById('uploadButton');
        const fileInput = document.getElementById('fileInput');
        
        // 既存のイベントリスナーを削除
        if (uploadButton) {
            uploadButton.removeEventListener('click', handleUploadButtonClick);
            // 新しいイベントリスナーを追加
            uploadButton.addEventListener('click', handleUploadButtonClick);
        }
    
        initializeSortButtons();
    }

    function initialize() {
        if (initialized) {
            console.log('VideoHandler already initialized');
            return Promise.resolve();
        }
        updateMetadataOptions();
        console.log('Initializing VideoHandler');
        return loadVideos().then(() => {
            initializeEventListeners();  // この行を追加
            initializeSortable();
            loadVideoDetails();
            updateTotalVideos();
            initialized = true;
        });
    }

    function initializeSortButtons() {
        console.log('Initializing sort buttons');
        const sortButtons = [
            { id: 'sortByUpload', criteria: 'upload', label: 'upload time' },
            { id: 'sortByCreation', criteria: 'creation', label: 'creation time' },
            { id: 'sortBySize', criteria: 'size', label: 'size' },
            { id: 'sortByDuration', criteria: 'duration', label: 'duration' }
        ];
    
        sortButtons.forEach(button => {
            const buttonElement = document.getElementById(button.id);
            if (buttonElement && !buttonElement.hasEventListener) {
                buttonElement.addEventListener('click', () => sortVideos(button.criteria));
                buttonElement.hasEventListener = true;
                console.log(`Sort by ${button.label} button initialized`);
            } else if (!buttonElement) {
                console.warn(`Button with id ${button.id} not found`);
            }
        });
    }

    function updateCurrentVideoDisplay() {
        const currentVideoNameElement = document.getElementById('currentVideoName');
        const currentVideoDurationElement = document.getElementById('currentVideoDuration');
        const currentVideoSizeElement = document.getElementById('currentVideoSize');
        const currentVideoResolutionElement = document.getElementById('currentVideoResolution');

        if (videos.length > 0) {
            const currentVideo = videos[0];
            if (currentVideoNameElement) currentVideoNameElement.textContent = currentVideo.filename;
            if (currentVideoDurationElement) currentVideoDurationElement.textContent = formatDuration(currentVideo.duration);
            if (currentVideoSizeElement) currentVideoSizeElement.textContent = (currentVideo.size / (1024 * 1024)).toFixed(2) + ' MB';
            if (currentVideoResolutionElement) currentVideoResolutionElement.textContent = currentVideo.resolution;
        } else {
            if (currentVideoNameElement) currentVideoNameElement.textContent = 'No video selected';
            if (currentVideoDurationElement) currentVideoDurationElement.textContent = '-';
            if (currentVideoSizeElement) currentVideoSizeElement.textContent = '-';
            if (currentVideoResolutionElement) currentVideoResolutionElement.textContent = '-';
        }
    }

    function formatDuration(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = Math.round(seconds % 60);
        return `${minutes} 分 ${remainingSeconds} 秒`;
    }

    function initializeSortable() {
        $("#videoList").sortable({
            items: ".video-item",
            handle: ".video-thumbnail",
            update: function(event, ui) {
                const newOrder = $(this).sortable('toArray', {attribute: 'data-filename'});
                videos = newOrder.map(filename => videos.find(v => v.filename === filename));
                updateVideoList();
            }
        });
    }
    
    function initializeEventListeners() {
        console.log('Initializing event listeners');
        const uploadButton = document.getElementById('uploadButton');
        const fileInput = document.getElementById('fileInput');
        
        // 既存のイベントリスナーを削除
        if (uploadButton) {
            uploadButton.removeEventListener('click', handleUploadButtonClick);
            // 新しいイベントリスナーを追加
            uploadButton.addEventListener('click', handleUploadButtonClick);
        }
    
        initializeSortButtons();
    }
    
    function handleUploadButtonClick() {
        const fileInput = document.getElementById('fileInput');
        const files = fileInput.files;
        if (files.length > 0) {
            VideoHandler.uploadFiles(files)
                .then(() => {
                    fileInput.value = '';
                    console.log('Upload completed successfully');
                })
                .catch(error => {
                    console.error('Upload failed:', error);
                    ErrorHandler.showError('Upload failed: ' + error.message);
                });
        } else {
            alert('アップロードするファイルを選択してください');
        }
    }

    // Public methods
    return {
        combineVideos: function() {
            const videos = this.getVideos();
            if (videos.length === 0) {
                alert('少なくとも1つの動画をアップロードしてください。');
                return;
            }
        
            const splitDuration = document.getElementById('splitOption').value;
            const resolution = document.getElementById('resolutionOption').value;
            const outputFileName = prompt('出力ファイル名を入力してください:', 'processed_video.mov');
            if (!outputFileName) return;
        
            const metadataDateSelect = document.getElementById('metadataDateSelect');
            const customVideoSelect = document.getElementById('customVideoSelect');
            let metadataSource = metadataDateSelect.value;
            let customVideoFilename = metadataSource === 'custom' ? customVideoSelect.value : null;
        
            console.log('Selected metadata source for processing:', metadataSource);
            console.log('Custom video filename (if applicable):', customVideoFilename);
        
            const videosWithOverlay = videos.map(video => ({
                filename: video.filename,
                overlay: video.overlay
            }));
        
            const requestBody = {
                input_files: videosWithOverlay,
                output_file: outputFileName,
                split_duration: splitDuration,
                resolution: resolution,
                metadata_source: metadataSource,
                custom_video_filename: customVideoFilename
            };
        
            console.log('Sending request to server:', JSON.stringify(requestBody));
        
            fetch('/process_videos', {
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
                        alert(`動画処理が完了し、分割されました。\n出力ファイル: ${data.split_files.join(', ')}\n作成日時: ${creationDate}`);
                    } else {
                        alert(`動画処理が完了しました。\n出力ファイル: ${data.output_file}\n作成日時: ${creationDate}`);
                    }
                } else {
                    throw new Error(data.error || '不明なエラーが発生しました');
                }
            })
            .catch(error => {
                console.error('動画処理エラー:', error);
                ErrorHandler.showError('動画処理エラー: ' + (error.message || '不明なエラー'));
            });
        },
        loadVideos: loadVideos,
        uploadFiles: uploadFiles,
        updateVideoList: updateVideoList,
        getVideos: () => videos,
        getCurrentVideoName: () => videos.length > 0 ? videos[0].filename : null,
        setVideos: (newVideos) => { videos = newVideos; updateVideoList(); },
        setCurrentVideoName: (name) => {
            const video = videos.find(v => v.filename === name);
            if (video) {
                videos = [video, ...videos.filter(v => v.filename !== name)];
                updateVideoList();
            }
        },
        initializeSortable: initializeSortable,
        addTextOverlay: addTextOverlay,
        sortVideos: sortVideos,
        initialize: initialize,
        initializeSortButtons: initializeSortButtons,
        initializeEventListeners: initializeEventListeners,
        updateTotalVideos: updateTotalVideos,
        loadVideoDetails: loadVideoDetails,
        formatDuration: formatDuration
    }

    function selectVideo(filename) {
        const videoFilenameInput = document.getElementById('videoFilename');
        if (videoFilenameInput) {
            videoFilenameInput.value = filename;
            alert(`Video "${filename}" selected for text overlay.`);
        }
    }
    
    // 既存のattachEventListeners関数内に以下を追加
    const selectBtn = element.querySelector('.select-video-btn');
    if (selectBtn) {
        selectBtn.addEventListener('click', function() {
            const filename = this.getAttribute('data-filename');
            selectVideo(filename);
        });
    }



    function updateMetadataOptions() {
        const metadataOptions = document.getElementById('metadataOptions');
        const customDateSelect = document.getElementById('customDateSelect');
        const customVideoSelect = document.getElementById('customVideoSelect');
        const metadataDateSelect = document.getElementById('metadataDateSelect');
    
        metadataOptions.style.display = 'block';
    
        metadataDateSelect.addEventListener('change', function() {
            console.log('Metadata source changed to:', this.value);
            if (this.value === 'custom') {
                customDateSelect.style.display = 'block';
                customVideoSelect.innerHTML = '';
                videos.forEach(video => {
                    const option = document.createElement('option');
                    option.value = video.filename;
                    option.textContent = `${video.filename} (${new Date(video.creationTime).toLocaleString()})`;
                    customVideoSelect.appendChild(option);
                });
            } else {
                customDateSelect.style.display = 'none';
            }
        });
    }

})();



// DOMContentLoaded イベントリスナーを1つに統合
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMの読み込みが完了しました');

    function initAll() {
        try {
            initializeExistingFunctionality();
            checkEventListeners();
            setupResetSessionButton();
        } catch (error) {
            console.error('Error during initialization:', error);
            ErrorHandler.showError('初期化中にエラーが発生しました: ' + error.message);
        }
    }

    if (typeof VideoHandler !== 'undefined' && typeof VideoHandler.initialize === 'function') {
        VideoHandler.initialize().then(() => {
            console.log('VideoHandler initialized');
            initializeExistingFunctionality();
        }).catch(error => {
            console.error('Error initializing VideoHandler:', error);
            initializeExistingFunctionality();
        });
    } else {
        console.error('VideoHandler or initialize method is not defined');
        initializeExistingFunctionality();
    }

    checkEventListeners();

    // Reset Session ボタンの設定
    const resetSessionButton = document.getElementById('resetSessionButton');
    if (resetSessionButton) {
        console.log('Reset Session button found');
        resetSessionButton.addEventListener('click', function() {
            console.log('Reset Session button clicked');
            if (confirm('セッションをリセットしますか？アップロードされたすべての動画がクリアされます。')) {
                fetch('/clear_session', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            alert('セッションが正常にリセットされました');
                            location.reload(); // ページをリロード
                        } else {
                            alert('セッションのリセットに失敗しました');
                        }
                    })
                    .catch(error => {
                        console.error('エラー:', error);
                        alert('セッションのリセット中にエラーが発生しました');
                    });
            }
        });
    } else {
        console.error('Reset Session button not found');
    }
});



function updateVideoDetails(videoItem, videoInfo) {
    try {
        const durationElement = videoItem.querySelector('.video-duration');
        const sizeElement = videoItem.querySelector('.video-size');
        const resolutionElement = videoItem.querySelector('.video-resolution');
        const creationTimeElement = videoItem.querySelector('.creation-time');
        const uploadTimeElement = videoItem.querySelector('.upload-time');

        if (durationElement && videoInfo.duration) 
            durationElement.textContent = formatDuration(videoInfo.duration);
        if (sizeElement && videoInfo.size) 
            sizeElement.textContent = `${(videoInfo.size / (1024 * 1024)).toFixed(2)}`;
        if (resolutionElement && videoInfo.resolution) 
            resolutionElement.textContent = videoInfo.resolution;
        if (creationTimeElement && videoInfo.creation_time) 
            creationTimeElement.textContent = `作成日時: ${formatDate(videoInfo.creation_time * 1000)}`;
        if (uploadTimeElement && videoInfo.upload_time) 
            uploadTimeElement.textContent = `アップロード日時: ${formatDate(videoInfo.upload_time * 1000)}`;
    } catch (error) {
        console.error('Error updating video details:', error);
        console.error('videoInfo:', JSON.stringify(videoInfo));
    }
}

function loadVideoDetails() {
    if (!videos || videos.length === 0) {
        console.log('No videos to load details for');
        return Promise.resolve();
    }

    const promises = videos.map(video => 
        fetch(`/video_info/${video.filename}`)
            .then(response => response.json())
            .then(data => {
                Object.assign(video, data);
                const videoItem = document.querySelector(`.video-item[data-filename="${video.filename}"]`);
                if (videoItem) {
                    updateVideoDetails(videoItem, video);
                }
            })
            .catch(error => {
                console.error(`Error fetching info for ${video.filename}:`, error);
            })
    );

    return Promise.all(promises);
}


function updateTotalVideos() {
    const totalVideosElement = document.getElementById('totalVideos');
    if (totalVideosElement) {
        totalVideosElement.textContent = VideoHandler.getVideos().length;
    }
}

function initializeExistingFunctionality() {
    if (typeof VideoHandler !== 'undefined') {
        if (typeof VideoHandler.initializeSortButtons === 'function') {
            VideoHandler.initializeSortButtons();
        } else {
            console.warn('VideoHandler.initializeSortButtons is not defined');
        }

        if (typeof VideoHandler.initializeEventListeners === 'function') {
            VideoHandler.initializeEventListeners();
        } else {
            console.warn('VideoHandler.initializeEventListeners is not defined');
        }
    }

    // モーダル関連の設定
    const closeModal = document.querySelector('.close');
    const modal = document.getElementById('textOverlayModal');
    if (closeModal && modal) {
        closeModal.addEventListener('click', function() {
            modal.style.display = 'none';
        });

        window.addEventListener('click', function(event) {
            if (event.target == modal) {
                modal.style.display = 'none';
            }
        });
    }
}

function checkEventListeners() {
    const uploadButton = document.getElementById('uploadButton');
    const sortByCreationBtn = document.getElementById('sortByCreation');

    if (uploadButton) {
        console.log('Upload button found');
    } else {
        console.error('Upload button not found');
    }

    if (sortByCreationBtn) {
        console.log('Sort by creation button found');
    } else {
        console.error('Sort by creation button not found');
    }
}

function showErrorToUser(message) {
    // エラーメッセージを表示するUIエレメントを作成
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.textContent = message;
    document.body.appendChild(errorDiv);

    // 5秒後にエラーメッセージを消す
    setTimeout(() => {
        errorDiv.remove();
    }, 5000);
}



document.addEventListener('DOMContentLoaded', checkEventListeners);

document.querySelector('.close').addEventListener('click', function() {
    document.getElementById('textOverlayModal').style.display = 'none';
});


window.addEventListener('click', function(event) {
    if (event.target == document.getElementById('textOverlayModal')) {
        document.getElementById('textOverlayModal').style.display = 'none';
    }
});
window.VideoHandler = VideoHandler;
window.formatDuration = VideoHandler.formatDuration;
