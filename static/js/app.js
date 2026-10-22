// Global state
let currentTask = null;
let currentImage = null;
let totalImages = 0;
let targetCount = 0;

const taskInput = document.getElementById('taskInput');
const loadBtn = document.getElementById('loadBtn');
const requirementView = document.getElementById('requirementView');
const imageDisplay = document.getElementById('imageDisplay');
const filterProgress = document.getElementById('filterProgress');
const acceptProgress = document.getElementById('acceptProgress');
const filterCount = document.getElementById('filterCount');
const acceptCount = document.getElementById('acceptCount');
const acceptBtn = document.getElementById('acceptBtn');
const rejectBtn = document.getElementById('rejectBtn');

// Event listeners
loadBtn.addEventListener('click', loadTask);
acceptBtn.addEventListener('click', markAccept);
rejectBtn.addEventListener('click', markReject);
taskInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') loadTask();
});

async function loadTask() {
    const taskName = taskInput.value.trim();
    
    if (!taskName) {
        showError('Please enter a Task name');
        return;
    }
    
    try {
        const response = await fetch('/api/load-task', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_name: taskName })
        });
        
        if (!response.ok) {
            const error = await response.json();
            showError(error.error || 'Failed to load task');
            return;
        }
        
        const data = await response.json();
        currentTask = taskName;
        totalImages = data.total_images;
        targetCount = data.target_count;
        
        // Update UI
        requirementView.value = data.requirements;
        updateProgress(data.processed_count, data.accepted_count);
        
        // Load first image
        await loadNextImage();
        
    } catch (error) {
        console.error('Error:', error);
        showError('Error loading task');
    }
}

async function loadNextImage() {
    if (!currentTask) return;
    
    try {
        const response = await fetch('/api/current-image');
        if (!response.ok) {
            showError('Failed to get current image');
            return;
        }
        
        const data = await response.json();
        
        if (!data.image) {
            imageDisplay.innerHTML = '<p>All images processed</p>';
            currentImage = null;
            acceptBtn.disabled = true;
            rejectBtn.disabled = true;
            return;
        }
        
        currentImage = data.image;
        
        // Load and display image
        const imgResponse = await fetch(`/api/image/${encodeURIComponent(currentImage)}`);
        if (!imgResponse.ok) {
            imageDisplay.innerHTML = '<p>Unable to load image</p>';
            return;
        }
        
        const blob = await imgResponse.blob();
        const url = URL.createObjectURL(blob);
        const img = document.createElement('img');
        img.src = url;
        imageDisplay.innerHTML = '';
        imageDisplay.appendChild(img);
        
        acceptBtn.disabled = false;
        rejectBtn.disabled = false;
        
    } catch (error) {
        console.error('Error loading image:', error);
        imageDisplay.innerHTML = '<p>Error loading image</p>';
    }
}

async function markAccept() {
    if (!currentImage) return;
    
    try {
        const response = await fetch('/api/mark-accept', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: currentImage })
        });
        
        if (!response.ok) {
            showError('Failed to mark image');
            return;
        }
        
        const data = await response.json();
        updateProgress(data.processed_count, data.accepted_count);
        await loadNextImage();
        
    } catch (error) {
        console.error('Error:', error);
        showError('Error marking image');
    }
}

async function markReject() {
    if (!currentImage) return;
    
    try {
        const response = await fetch('/api/mark-reject', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: currentImage })
        });
        
        if (!response.ok) {
            showError('Failed to mark image');
            return;
        }
        
        const data = await response.json();
        updateProgress(data.processed_count, data.accepted_count);
        await loadNextImage();
        
    } catch (error) {
        console.error('Error:', error);
        showError('Error marking image');
    }
}

function updateProgress(processed, accepted) {
    // Update filter progress
    const filterPercent = totalImages > 0 ? (processed / totalImages) * 100 : 0;
    filterProgress.style.width = filterPercent + '%';
    filterCount.textContent = `${processed}/${totalImages}`;
    
    // Update accept progress
    const acceptPercent = targetCount > 0 ? (accepted / targetCount) * 100 : 0;
    acceptProgress.style.width = Math.min(acceptPercent, 100) + '%';
    acceptCount.textContent = `${accepted}/${targetCount}`;
}

function showError(message) {
    alert(message); // Simple for now; can enhance with toast notifications
}

// Initialize
window.addEventListener('load', () => {
    acceptBtn.disabled = true;
    rejectBtn.disabled = true;
});
