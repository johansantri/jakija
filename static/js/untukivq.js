// static/js/in-video-quiz.js
// Versi FINAL - Fix restore jawaban lama dari DB + tampil otomatis saat timeupdate

const quizState = {
    quizzes: [],
    score: 0,
    answeredQuizzes: {},  // { 0: {answered: true, correct: true, userAnswer: "A", shown: true/false} }
    currentQuizIndex: 0,
    video: null,
    overlay: null,
    quizCard: null,
    questionText: null,
    optionsContainer: null,
    nextButton: null,
    explanation: null,
    scoreDisplay: null
};

function getCSRFToken() {
    const name = "csrftoken=";
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.startsWith(name)) return cookie.substring(name.length);
    }
    return null;
}

function playSound(correct) {
    const sound = correct ? document.getElementById('correctSound') : document.getElementById('wrongSound');
    if (sound) {
        sound.pause();
        sound.currentTime = 0;
        sound.play().catch(() => {});
    }
}

function updateScoreDisplay() {
    const answeredCount = Object.keys(quizState.answeredQuizzes).length;
    if (quizState.scoreDisplay) {
        quizState.scoreDisplay.textContent = `${quizState.score} / ${answeredCount}`;
    }
}

function continueWatching() {
    if (quizState.video && quizState.video.paused) {
        quizState.video.play();
    }
    quizState.overlay.classList.remove('active');
}

function endQuiz() {
    const videoEl = quizState.video;
    const assessmentId = videoEl.dataset.assessment;

    quizState.overlay.classList.add('active');

    fetch(`/video/${videoEl.dataset.id}/save-result/${assessmentId}/`, {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCSRFToken(),
        },
        body: JSON.stringify({
            score: quizState.score,
            total: quizState.quizzes.length,
            answers: quizState.answeredQuizzes
        })
    })
    .then(res => res.ok ? res.json() : res.text().then(text => { throw new Error(text) }))
    .then(data => console.log("Saved:", data))
    .catch(err => {
        console.error("Save failed:", err);
        alert('Gagal menyimpan hasil quiz.');
    });

    quizState.quizCard.innerHTML = `
        <div class="text-center py-12">
            <i class="fas fa-trophy text-8xl text-yellow-400 mb-6 finish-card-icon"></i>
            <h2 class="text-4xl font-bold mb-4">Done!</h2>
            <p class="text-6xl font-black text-green-400">${quizState.score}/${quizState.quizzes.length}</p>
            <button onclick="continueWatching()" class="mt-8 w-full bg-green-600 hover:bg-green-700 text-white font-bold py-5 rounded-full text-xl">
                Continue Watching Until Finished
            </button>
        </div>`;
}

function showQuiz(index) {
    const q = quizState.quizzes[index];
    quizState.video.pause();
    quizState.overlay.classList.add('active');
    gsap.to(quizState.quizCard, {scale: 1, opacity: 1, duration: 0.6, ease: "back.out(1.7)"});

    quizState.questionText.textContent = q.question;
    quizState.optionsContainer.innerHTML = '';
    quizState.explanation.classList.add('hidden');
    quizState.nextButton.classList.add('hidden');

    const alreadyAnswered = quizState.answeredQuizzes[index];

    // Kalau sudah dijawab sebelumnya → tampilkan dalam mode "review" (disabled + explanation + continue)
    if (alreadyAnswered && alreadyAnswered.answered) {
        renderAnsweredView(q, index, alreadyAnswered);
        quizState.explanation.textContent = q.explanation || "";
        quizState.explanation.classList.remove('hidden');
        quizState.nextButton.classList.remove('hidden');
        return;
    }

    // Kalau belum dijawab → tampilkan mode normal dengan input
    renderFreshQuiz(q, index);
}

function renderAnsweredView(q, index, answeredData) {
    if (q.type === "multiple-choice") {
        q.options.forEach((opt, i) => {
            const btn = document.createElement('button');
            btn.className = "w-full p-4 text-center rounded-xl font-medium text-base md:text-lg disabled:opacity-75";
            btn.textContent = opt;
            btn.disabled = true;
            if (i === q.correct) btn.classList.add("bg-green-500", "text-white");
            if (i === answeredData.userAnswer && !answeredData.correct) btn.classList.add("bg-red-500", "text-white");
            else btn.classList.add("bg-gray-100");
            quizState.optionsContainer.appendChild(btn);
        });
    } else if (q.type === "true-false") {
        ["incorrect", "correct"].forEach(label => {
            const btn = document.createElement('button');
            btn.className = "w-full p-6 text-2xl font-bold rounded-xl text-white mb-4";
            btn.textContent = label;
            btn.disabled = true;
            const isCorrect = label === "correct";
            if (isCorrect) btn.classList.add("bg-green-500");
            else btn.classList.add("bg-red-500");
            if (answeredData.userAnswer === label && !answeredData.correct) {
                btn.classList.remove("bg-green-500");
                btn.classList.add("bg-red-500");
            }
            quizState.optionsContainer.appendChild(btn);
        });
    } else if (q.type === "fill-blank" || q.type === "es") {
        const input = document.createElement('input');
        input.type = "text";
        input.value = answeredData.userAnswer || "";
        input.disabled = true;
        input.className = "w-full p-5 text-xl text-center border-4 border-gray-300 rounded-xl outline-none " +
                         (answeredData.correct ? "bg-green-500 text-white" : "bg-red-500 text-white");
        quizState.optionsContainer.appendChild(input);
    } else if (q.type === "drag-and-drop") {
        const drop = document.createElement('div');
        drop.className = "border-4 border-dashed border-green-500 rounded-2xl h-32 mb-6 flex items-center justify-center text-lg font-bold";
        drop.textContent = answeredData.userAnswer || "Answer: " + q.correct;
        quizState.optionsContainer.appendChild(drop);
    }
}

function renderFreshQuiz(q, index) {
    const handleAnswer = (correct, element) => {
        quizState.answeredQuizzes[index] = {
            answered: true,
            correct: correct,
            userAnswer: element ? (element.value || element.textContent || element.dataset?.value) : null,
            shown: true
        };
        if (correct) quizState.score++;
        playSound(correct);
        if (element) element.classList.add(correct ? "bg-green-500" : "bg-red-500", "text-white");
        quizState.explanation.textContent = q.explanation || "";
        quizState.explanation.classList.remove('hidden');
        quizState.nextButton.classList.remove('hidden');
        updateScoreDisplay();
    };

    if (q.type === "multiple-choice") {
        q.options.forEach((opt, i) => {
            const btn = document.createElement('button');
            btn.className = "w-full p-4 text-center bg-blue-100 hover:bg-indigo-200 rounded-xl font-medium transition text-base md:text-lg";
            btn.textContent = opt;
            btn.onclick = () => handleAnswer(i === q.correct, btn);
            quizState.optionsContainer.appendChild(btn);
        });
    } else if (q.type === "true-false") {
        const correctIsTrue = String(q.correct).toLowerCase() === "true" || String(q.correct).toLowerCase() === "correct";

        const incorrectBtn = document.createElement('button');
        incorrectBtn.className = "w-full p-6 text-2xl font-bold rounded-xl bg-red-500 hover:bg-red-600 text-white mb-4";
        incorrectBtn.textContent = "incorrect";
        incorrectBtn.onclick = () => handleAnswer(!correctIsTrue, incorrectBtn);

        const correctBtn = document.createElement('button');
        correctBtn.className = "w-full p-6 text-2xl font-bold rounded-xl bg-green-500 hover:bg-green-600 text-white";
        correctBtn.textContent = "correct";
        correctBtn.onclick = () => handleAnswer(correctIsTrue, correctBtn);

        quizState.optionsContainer.appendChild(incorrectBtn);
        quizState.optionsContainer.appendChild(correctBtn);
    } else if (q.type === "fill-blank" || q.type === "es") {
        const input = document.createElement('input');
        input.type = "text";
        input.autofocus = true;
        input.placeholder = "Type your answer...";
        input.className = "w-full p-5 text-xl text-center border-4 border-gray-300 rounded-xl focus:border-emerald-500 outline-none";

        const submit = document.createElement('button');
        submit.textContent = "Submit";
        submit.className = "mt-4 w-full bg-green-600 hover:bg-green-700 text-white font-bold py-4 rounded-full";
        submit.onclick = () => handleAnswer(input.value.trim().toLowerCase() === q.correct.toLowerCase(), input);

        input.addEventListener('keydown', e => e.key === 'Enter' && submit.click());
        quizState.optionsContainer.appendChild(input);
        quizState.optionsContainer.appendChild(submit);
    } else if (q.type === "drag-and-drop") {
        const dropZone = document.createElement('div');
        dropZone.className = "border-4 border-dashed border-green-500 rounded-2xl h-32 mb-6 flex items-center justify-center text-lg font-bold";
        dropZone.textContent = "Drop here";
        dropZone.ondragover = e => e.preventDefault();
        dropZone.ondrop = e => {
            e.preventDefault();
            const text = e.dataTransfer.getData("text");
            handleAnswer(text === q.correct, dropZone);
        };
        quizState.optionsContainer.appendChild(dropZone);

        const items = document.createElement('div');
        items.className = "grid grid-cols-2 gap-4";
        q.items.forEach(item => {
            const el = document.createElement('div');
            el.className = "bg-green-600 text-white p-5 rounded-xl text-center cursor-move select-none text-base md:text-lg";
            el.textContent = item;
            el.draggable = true;
            el.ondragstart = e => e.dataTransfer.setData("text", item);
            items.appendChild(el);
        });
        quizState.optionsContainer.appendChild(items);
    }
}

function setupNextButton() {
    if (quizState.nextButton) {
        quizState.nextButton.onclick = () => {
            quizState.overlay.classList.remove('active');
            quizState.currentQuizIndex++;
            if (quizState.currentQuizIndex < quizState.quizzes.length) {
                quizState.video.play();
            } else {
                endQuiz();
            }
        };
    }
}

function handleTimeUpdate() {
    quizState.quizzes.forEach((q, index) => {
        const answered = quizState.answeredQuizzes[index];
        // Hanya tampilkan kalau waktu sudah lewat DAN (belum dijawab ATAU sudah dijawab tapi belum ditampilkan overlay-nya)
        if (quizState.video.currentTime >= q.time && (!answered || !answered.shown)) {
            // Tandai sebagai sudah ditampilkan di sesi ini
            if (!answered) {
                quizState.answeredQuizzes[index] = { shown: true };
            } else {
                answered.shown = true;
            }
            showQuiz(index);
        }
    });
}

function initVideoQuiz() {
    const video = document.getElementById('myVideo');
    if (!video) return;

    // Setup elemen DOM
    quizState.video = video;
    quizState.overlay = document.getElementById('quizOverlay');
    quizState.quizCard = document.querySelector('.quiz-card');
    quizState.questionText = document.getElementById('questionText');
    quizState.optionsContainer = document.getElementById('optionsContainer');
    quizState.nextButton = document.getElementById('nextButton');
    quizState.explanation = document.getElementById('explanation');
    quizState.scoreDisplay = document.getElementById('scoreDisplay');

    // Load data dari attribute
    quizState.quizzes = JSON.parse(video.dataset.quizzes || '[]');
    const resultJson = video.dataset.resultJson || 'null';
    const result = resultJson !== 'null' ? JSON.parse(resultJson) : null;

    // Reset state
    quizState.score = 0;
    quizState.answeredQuizzes = {};
    quizState.currentQuizIndex = 0;

    if (result) {
        quizState.score = result.score || 0;
        if (result.answers) {
            quizState.answeredQuizzes = {};
            Object.entries(result.answers).forEach(([key, saved]) => {
                quizState.answeredQuizzes[key] = {
                    answered: true,
                    correct: saved.correct || false,
                    userAnswer: saved.userAnswer !== undefined ? saved.userAnswer : null,  // PASTIKAN INI ADA!
                    //shown: true  // langsung true supaya langsung muncul saat timeupdate
                };
            });
        }
    }

    updateScoreDisplay();
    setupNextButton();

    // Event listener timeupdate (hapus dulu biar ga duplikat)
    video.removeEventListener('timeupdate', handleTimeUpdate);
    video.addEventListener('timeupdate', handleTimeUpdate);
}

// HTMX swap handler
document.body.addEventListener('htmx:afterSwap', (evt) => {
    if (evt.detail.target.id === 'content-area') {
        setTimeout(initVideoQuiz, 100);
    }
});

// Initial load
document.addEventListener('DOMContentLoaded', initVideoQuiz);