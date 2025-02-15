function updateScheduleInterface() {
    const scheduleType = document.getElementById('schedule_type').value;
    const interfaces = ['hourly_schedule', 'daily_schedule', 'weekly_schedule', 'advanced_schedule'];
    
    // Hide all interfaces first
    interfaces.forEach(id => {
        document.getElementById(id).style.display = 'none';
    });
    
    // Show selected interface
    if (scheduleType !== 'manual') {
        document.getElementById(scheduleType + '_schedule').style.display = 'block';
    }
}

function generateSchedule() {
    const scheduleType = document.getElementById('schedule_type').value;
    let schedule = '';
    
    if (scheduleType === 'hourly') {
        const interval = document.getElementById('hours_interval').value;
        const minute = document.getElementById('start_minute').value;
        if (interval === '1') {
            schedule = `${minute} * * * *`; // Every hour at specified minute
        } else {
            schedule = `${minute} */${interval} * * *`; // Every X hours at specified minute
        }
    } else if (scheduleType === 'daily') {
        const time = document.getElementById('daily_time').value.split(':');
        schedule = `${time[1]} ${time[0]} * * *`; // Every day at specified time
    } else if (scheduleType === 'weekly') {
        const time = document.getElementById('weekly_time').value.split(':');
        const selectedDays = Array.from(document.querySelectorAll('input[name="weekdays"]:checked'))
            .map(cb => cb.value)
            .join(',');
        schedule = selectedDays ? `${time[1]} ${time[0]} * * ${selectedDays}` : ''; // Selected days at specified time
    } else if (scheduleType === 'advanced') {
        schedule = document.getElementById('cron').value;
    }
    
    document.getElementById('schedule').value = schedule;
    return schedule !== '' || scheduleType === 'manual';
}

// Initialize interface on page load
document.addEventListener('DOMContentLoaded', function() {
    const scheduleType = document.getElementById('schedule_type');
    const schedule = document.getElementById('schedule').value.trim();
    
    if (schedule) {
        const parts = schedule.split(' ');
        if (parts.length === 5) {
            // Check for advanced cron patterns first
            if (parts.some(part => 
                part.includes('/') && !part.startsWith('*/') || // Contains step values other than */n
                part.includes('-') || // Contains ranges
                /[a-zA-Z]/.test(part) || // Contains letters (e.g., JAN, MON)
                part.includes('#') || // Contains day of week modifiers
                part.includes('L') || // Contains 'last' modifier
                part.includes('W') || // Contains 'weekday' modifier
                part.includes('?') // Contains optional value marker
            ) || 
            schedule === '* * * * *' || // Special case for every minute
            parts[0].startsWith('*/') || // Special case for every n minutes
            (parts[0] === '*' && parts[1] === '*')) { // Special case for every minute of every hour
                scheduleType.value = 'advanced';
                document.getElementById('cron').value = schedule;
            }
            // Then try to detect hourly schedule (must have specific minute)
            else if ((parts[1].includes('*/') || parts[1] === '*') && 
                    /^\d+$/.test(parts[0]) && // Must be a specific minute
                    parts[2] === '*' && parts[3] === '*' && parts[4] === '*') {
                scheduleType.value = 'hourly';
                document.getElementById('start_minute').value = parseInt(parts[0]) || 0;
                document.getElementById('hours_interval').value = parts[1].includes('*/') ? 
                    parseInt(parts[1].replace('*/', '')) : 1;
            } 
            // Then try to detect daily schedule
            else if (parts[2] === '*' && parts[3] === '*' && parts[4] === '*' &&
                    /^\d+$/.test(parts[0]) && /^\d+$/.test(parts[1])) {
                scheduleType.value = 'daily';
                document.getElementById('daily_time').value = 
                    `${parts[1].padStart(2, '0')}:${parts[0].padStart(2, '0')}`;
            } 
            // Then try to detect weekly schedule
            else if (parts[2] === '*' && parts[3] === '*' && 
                    (parts[4].includes(',') || /^[1-7]$/.test(parts[4])) &&
                    /^\d+$/.test(parts[0]) && /^\d+$/.test(parts[1])) {
                scheduleType.value = 'weekly';
                document.getElementById('weekly_time').value = 
                    `${parts[1].padStart(2, '0')}:${parts[0].padStart(2, '0')}`;
                const days = parts[4].split(',');
                days.forEach(day => {
                    const checkbox = document.querySelector(`input[name="weekdays"][value="${day}"]`);
                    if (checkbox) checkbox.checked = true;
                });
            } 
            // If none of the above patterns match exactly, treat as advanced cron
            else {
                scheduleType.value = 'advanced';
                document.getElementById('cron').value = schedule;
            }
        } else if (schedule === '') {
            scheduleType.value = 'manual';
        } else {
            // If schedule doesn't match expected format, set as advanced
            scheduleType.value = 'advanced';
            document.getElementById('cron').value = schedule;
        }
    } else {
        scheduleType.value = 'manual';
    }
    
    // Make sure to update the interface after setting the schedule type
    updateScheduleInterface();
    
    // Add event listener for schedule type changes
    scheduleType.addEventListener('change', function() {
        updateScheduleInterface();
        generateSchedule(); // Generate schedule when type changes
    });
    
    // Add event listeners for all schedule inputs to auto-update the schedule
    document.querySelectorAll('.schedule-interface input, .schedule-interface select').forEach(input => {
        input.addEventListener('change', generateSchedule);
    });
}); 