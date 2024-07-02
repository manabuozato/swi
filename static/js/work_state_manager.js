const WorkStateManager = (function() {
    function saveWorkState() {
        console.log('Saving work state...');

        const workState = {
            videos: VideoHandler.getVideos(),
            currentVideo: VideoHandler.getCurrentVideoName(),
            timestamp: new Date().toISOString(),
        };
        
        const defaultName = new Date().toISOString().replace(/[:.]/g, '-');
        document.getElementById('stateNameInput').value = defaultName;
        document.getElementById('saveStateModal').style.display = 'block';

        document.getElementById('confirmSaveState').onclick = function() {
            const stateName = document.getElementById('stateNameInput').value;
            document.getElementById('saveStateModal').style.display = 'none';
            
            fetch('/save_work_state', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    name: stateName,
                    state: workState
                })
            })
            .then(handleFetchErrors)
            .then(data => {
                if (data.success) {
                    console.log('Work state saved successfully');
                    alert('Work state saved successfully. Name: ' + data.name);
                    updateSavedStatesList();
                } else {
                    throw new Error(data.error || 'Unknown error occurred');
                }
            })
            .catch(error => {
                console.error('Error saving work state:', error);
                alert('Error saving work state: ' + error.message);
            });
        };

        document.getElementById('cancelSaveState').onclick = function() {
            document.getElementById('saveStateModal').style.display = 'none';
        };
    }

    function loadWorkState(stateName) {
        console.log('Loading work state:', stateName);

        fetch(`/load_work_state/${encodeURIComponent(stateName)}`)
        .then(handleFetchErrors)
        .then(data => {
            console.log('Received work state:', data);
            VideoHandler.setVideos(data.videos || []);
            VideoHandler.setCurrentVideoName(data.currentVideo || '');
            updateUI();
            alert('Work state loaded successfully');
        })
        .catch(error => {
            console.error('Error loading work state:', error);
            alert('Error loading work state: ' + error.message);
        });
    }

    function updateUI() {
        console.log('Updating UI with loaded state');
        VideoHandler.updateVideoList();
        VideoHandler.updateCurrentVideoDisplay();
    }

    function updateSavedStatesList() {
        fetch('/get_saved_states')
            .then(handleFetchErrors)
            .then(states => {
                const select = document.getElementById('savedStatesSelect');
                select.innerHTML = '';
                states.forEach(state => {
                    const option = document.createElement('option');
                    option.value = state.name;
                    option.textContent = `${state.name} (${new Date(state.timestamp).toLocaleString()})`;
                    select.appendChild(option);
                });
            })
            .catch(error => {
                console.error('Error updating saved states list:', error);
            });
    }

    function handleFetchErrors(response) {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    }

    function deleteWorkState(stateName) {
        if (confirm(`Are you sure you want to delete the state "${stateName}"?`)) {
            fetch(`/delete_work_state/${encodeURIComponent(stateName)}`, { method: 'POST' })
                .then(handleFetchErrors)
                .then(data => {
                    if (data.success) {
                        alert('Work state deleted successfully');
                        updateSavedStatesList();
                    } else {
                        throw new Error(data.error || 'Unknown error occurred');
                    }
                })
                .catch(error => {
                    console.error('Error deleting work state:', error);
                    alert('Error deleting work state: ' + error.message);
                });
        }
    }

    return {
        saveWorkState: saveWorkState,
        loadWorkState: loadWorkState,
        updateSavedStatesList: updateSavedStatesList,
        deleteWorkState: deleteWorkState
    };
    document.addEventListener('DOMContentLoaded', function() {
        WorkStateManager.updateSavedStatesList();
        
        const saveStateButton = document.getElementById('saveStateButton');
        if (saveStateButton) {
            saveStateButton.addEventListener('click', WorkStateManager.saveWorkState);
        }
    
        const loadStateButton = document.getElementById('loadStateButton');
        if (loadStateButton) {
            loadStateButton.addEventListener('click', function() {
                const select = document.getElementById('savedStatesSelect');
                if (select && select.value) {
                    WorkStateManager.loadWorkState(select.value);
                } else {
                    alert('Please select a saved state to load');
                }
            });
        }
    });
})();

