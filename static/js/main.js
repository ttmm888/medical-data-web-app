// static/js/main.js

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
    
    // Initialize all components
    initializeFormValidation();
    initializeAutoResize();
    initializeFileUpload();
    initializeSearchEnhancements();
    initializeTooltips();
    
    // Auto-dismiss alerts after 5 seconds
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(alert => {
            if (alert.querySelector('.btn-close')) {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }
        });
    }, 5000);
});

/**
 * Initialize form validation with real-time feedback
 */
function initializeFormValidation() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        // Add validation to required fields
        const requiredFields = form.querySelectorAll('input[required], select[required], textarea[required]');
        
        requiredFields.forEach(field => {
            // Validate on blur
            field.addEventListener('blur', function() {
                validateField(this);
            });
            
            // Clear validation on input
            field.addEventListener('input', function() {
                this.classList.remove('is-invalid', 'is-valid');
                removeFieldError(this);
            });
        });
        
        // Handle form submission
        form.addEventListener('submit', function(e) {
            let isValid = true;
            
            // Validate all required fields
            requiredFields.forEach(field => {
                if (!validateField(field)) {
                    isValid = false;
                }
            });
            
            // Additional custom validations
            if (isValid) {
                isValid = performCustomValidations(form);
            }
            
            if (!isValid) {
                e.preventDefault();
                showFormErrors();
                return false;
            }
            
            // Show loading state
            showLoadingState(form);
        });
    });
}

/**
 * Validate individual field
 */
function validateField(field) {
    const value = field.value.trim();
    let isValid = true;
    let errorMessage = '';
    
    // Check required fields
    if (field.hasAttribute('required') && !value) {
        isValid = false;
        errorMessage = 'This field is required.';
    }
    
    // Check minimum length
    const minLength = field.getAttribute('minlength');
    if (minLength && value.length < parseInt(minLength)) {
        isValid = false;
        errorMessage = `Minimum ${minLength} characters required.`;
    }
    
    // Email validation
    if (field.type === 'email' && value) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(value)) {
            isValid = false;
            errorMessage = 'Please enter a valid email address.';
        }
    }
    
    // Date validation
    if (field.type === 'date' && value) {
        const selectedDate = new Date(value);
        const today = new Date();
        
        if (field.name === 'date_of_birth' && selectedDate > today) {
            isValid = false;
            errorMessage = 'Date of birth cannot be in the future.';
        }
    }
    
    // Update field appearance
    if (isValid) {
        field.classList.remove('is-invalid');
        field.classList.add('is-valid');
        removeFieldError(field);
    } else {
        field.classList.remove('is-valid');
        field.classList.add('is-invalid');
        showFieldError(field, errorMessage);
    }
    
    return isValid;
}

/**
 * Show field-specific error message
 */
function showFieldError(field, message) {
    removeFieldError(field);
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'invalid-feedback d-block';
    errorDiv.textContent = message;
    errorDiv.setAttribute('data-field-error', field.name);
    
    field.parentNode.appendChild(errorDiv);
}

/**
 * Remove field-specific error message
 */
function removeFieldError(field) {
    const existingError = field.parentNode.querySelector(`[data-field-error="${field.name}"]`);
    if (existingError) {
        existingError.remove();
    }
}

/**
 * Perform custom form validations
 */
function performCustomValidations(form) {
    let isValid = true;
    
    // Check for duplicate entries in textareas
    const textareas = form.querySelectorAll('textarea[name="doctor"], textarea[name="medication"], textarea[name="diagnosis"]');
    textareas.forEach(textarea => {
        if (textarea.value.trim()) {
            const items = textarea.value.split(/[,\n]/).map(item => item.trim()).filter(item => item);
            const uniqueItems = [...new Set(items.map(item => item.toLowerCase()))];
            
            if (items.length !== uniqueItems.length) {
                showFieldError(textarea, 'Duplicate entries detected. Please remove duplicates.');
                textarea.classList.add('is-invalid');
                isValid = false;
            }
        }
    });
    
    return isValid;
}

/**
 * Show form errors summary
 */
function showFormErrors() {
    const firstInvalidField = document.querySelector('.is-invalid');
    if (firstInvalidField) {
        firstInvalidField.focus();
        firstInvalidField.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
    // Show general error message
    showAlert('Please correct the errors below and try again.', 'danger');
}

/**
 * Show loading state for form submission
 */
function showLoadingState(form) {
    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) {
        submitBtn.classList.add('loading');
        submitBtn.disabled = true;
        
        // Re-enable after timeout (in case of server issues)
        setTimeout(() => {
            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
        }, 30000);
    }
}

/**
 * Initialize auto-resize for textareas
 */
function initializeAutoResize() {
    const textareas = document.querySelectorAll('textarea');
    
    textareas.forEach(textarea => {
        // Set initial height
        autoResize(textarea);
        
        // Add event listeners
        textarea.addEventListener('input', function() {
            autoResize(this);
        });
        
        textarea.addEventListener('paste', function() {
            setTimeout(() => autoResize(this), 100);
        });
    });
}

/**
 * Auto-resize textarea to fit content
 */
function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.max(textarea.scrollHeight, 100) + 'px';
}

/**
 * Initialize file upload enhancements
 */
function initializeFileUpload() {
    const fileInputs = document.querySelectorAll('input[type="file"]');
    
    fileInputs.forEach(input => {
        const container = input.closest('.file-upload-area') || input.parentNode;
        
        // Add drag and drop functionality
        container.addEventListener('dragover', function(e) {
            e.preventDefault();
            this.classList.add('dragover');
        });
        
        container.addEventListener('dragleave', function(e) {
            e.preventDefault();
            this.classList.remove('dragover');
        });
        
        container.addEventListener('drop', function(e) {
            e.preventDefault();
            this.classList.remove('dragover');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                input.files = files;
                handleFileSelection(input);
            }
        });
        
        // Handle file selection
        input.addEventListener('change', function() {
            handleFileSelection(this);
        });
    });
}

/**
 * Handle file selection and validation
 */
function handleFileSelection(input) {
    const file = input.files[0];
    if (!file) return;
    
    // Validate file size (16MB limit)
    const maxSize = 16 * 1024 * 1024; // 16MB
    if (file.size > maxSize) {
        showAlert('File size must be less than 16MB.', 'danger');
        input.value = '';
        return;
    }
    
    // Validate file type
    const allowedTypes = ['pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx'];
    const fileExtension = file.name.split('.').pop().toLowerCase();
    
    if (!allowedTypes.includes(fileExtension)) {
        showAlert('Invalid file type. Allowed types: PDF, Images, Word documents.', 'danger');
        input.value = '';
        return;
    }
    
    // Show file info
    showFileInfo(input, file);
}

/**
 * Show selected file information
 */
function showFileInfo(input, file) {
    const infoDiv = input.parentNode.querySelector('.file-info') || document.createElement('div');
    infoDiv.className = 'file-info mt-2 p-2 bg-light rounded';
    
    const sizeInMB = (file.size / (1024 * 1024)).toFixed(2);
    infoDiv.innerHTML = `
        <small class="text-muted">
            <i class="bi bi-file-earmark me-1"></i>
            <strong>${file.name}</strong> (${sizeInMB} MB)
        </small>
    `;
    
    if (!input.parentNode.querySelector('.file-info')) {
        input.parentNode.appendChild(infoDiv);
    }
}

/**
 * Initialize search enhancements
 */
function initializeSearchEnhancements() {
    const searchForm = document.querySelector('form[action*="search"]');
    if (!searchForm) return;
    
    const searchInput = searchForm.querySelector('input[name="query"]');
    if (!searchInput) return;
    
    // Add search suggestions (if implementing autocomplete later)
    searchInput.addEventListener('input', function() {
        const query = this.value.trim();
        if (query.length >= 2) {
            // Implement search suggestions here if needed
            debounce(performSearch, 300)(query);
        }
    });
    
    // Handle search form submission
    searchForm.addEventListener('submit', function(e) {
        const query = searchInput.value.trim();
        if (!query) {
            e.preventDefault();
            showAlert('Please enter a search term.', 'warning');
            searchInput.focus();
        }
    });
}

/**
 * Debounce function for search
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Perform search (placeholder for future implementation)
 */
function performSearch(query) {
    // This can be enhanced to show live search results
    console.log('Searching for:', query);
}

/**
 * Initialize Bootstrap tooltips
 */
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

/**
 * Show alert message
 */
function showAlert(message, type = 'info') {
    const alertContainer = document.querySelector('.container');
    if (!alertContainer) return;
    
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            <i class="bi bi-${getAlertIcon(type)} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    // Insert at the top of the container
    alertContainer.insertAdjacentHTML('afterbegin', alertHtml);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        const alert = alertContainer.querySelector('.alert:first-child');
        if (alert && alert.querySelector('.btn-close')) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }
    }, 5000);
}

/**
 * Get appropriate icon for alert type
 */
function getAlertIcon(type) {
    const icons = {
        'success': 'check-circle',
        'danger': 'exclamation-circle',
        'warning': 'exclamation-triangle',
        'info': 'info-circle'
    };
    return icons[type] || 'info-circle';
}

/**
 * Utility function to format dates
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

/**
 * Utility function to calculate age from date of birth
 */
function calculateAge(dateOfBirth) {
    const today = new Date();
    const birth = new Date(dateOfBirth);
    let age = today.getFullYear() - birth.getFullYear();
    const monthDiff = today.getMonth() - birth.getMonth();
    
    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
        age--;
    }
    
    return age;
}

/**
 * Smooth scroll to element
 */
function scrollToElement(element, offset = 100) {
    const elementPosition = element.getBoundingClientRect().top;
    const offsetPosition = elementPosition + window.pageYOffset - offset;
    
    window.scrollTo({
        top: offsetPosition,
        behavior: 'smooth'
    });
}

// Export functions for use in other scripts
window.MedicalApp = {
    showAlert,
    validateField,
    calculateAge,
    formatDate,
    scrollToElement
};