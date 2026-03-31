(function() {
    const courseData = document.getElementById('course-data');
    const courseId = courseData.dataset.courseId;
    const csrfToken = courseData.dataset.csrfToken;

    function pingLearningSession() {
        fetch("/partner/ping-session/", { // Replace with the actual URL
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ course_id: courseId })
        });
    }

    setInterval(pingLearningSession, 60000);
})();