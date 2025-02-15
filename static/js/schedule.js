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
    const schedule = document.getElementById('schedule').value;
    
    if (schedule) {
        const parts = schedule.split(' ');
        if (parts.length === 5) {
            if (parts[1].includes('*/')) {
                // Hourly interval
                scheduleType.value = 'hourly';
                document.getElementById('start_minute').value = parts[0];
                document.getElementById('hours_interval').value = parts[1].replace('*/', '');
            } else if (parts[3] === '*' && parts[4] === '*') {
                // Daily schedule
                scheduleType.value = 'daily';
                document.getElementById('daily_time').value = 
                    `${parts[1].padStart(2, '0')}:${parts[0].padStart(2, '0')}`;
            } else if (parts[4].includes(',') || /^\d+$/.test(parts[4])) {
                // Weekly schedule
                scheduleType.value = 'weekly';
                document.getElementById('weekly_time').value = 
                    `${parts[1].padStart(2, '0')}:${parts[0].padStart(2, '0')}`;
                const days = parts[4].split(',');
                days.forEach(day => {
                    const checkbox = document.querySelector(`input[name="weekdays"][value="${day}"]`);
                    if (checkbox) checkbox.checked = true;
                });
            } else {
                // Advanced cron
                scheduleType.value = 'advanced';
                document.getElementById('cron').value = schedule;
            }
            updateScheduleInterface();
        }
    }
}); 