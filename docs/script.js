(() => {
  const root = document.documentElement
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)")
  const revealItems = [...document.querySelectorAll("[data-reveal]")]
  const counter = document.querySelector(".stat-number")
  const currentGrid = document.querySelector(".current-people-grid") || document.querySelector(".people-grid")
  const formerGrid = document.querySelector(".former-people-grid")
  const randomUnit = () => {
    if (window.crypto?.getRandomValues) {
      return window.crypto.getRandomValues(new Uint32Array(1))[0] / 2 ** 32
    }

    return Math.random()
  }
  const shuffle = cards => {
    const shuffled = [...cards]

    for (let index = shuffled.length - 1; index > 0; index -= 1) {
      const swapIndex = Math.floor(randomUnit() * (index + 1))
      const current = shuffled[index]
      shuffled[index] = shuffled[swapIndex]
      shuffled[swapIndex] = current
    }

    return shuffled
  }
  const currentCards = currentGrid ? [...currentGrid.querySelectorAll(".person-card")] : []
  const formerCards = formerGrid ? [...formerGrid.querySelectorAll(".person-card")] : []
  const mutualCards = currentCards.filter(card => card.dataset.mutual === "true")
  const otherCards = currentCards.filter(card => card.dataset.mutual !== "true")
  const orderedCurrentCards = [...shuffle(mutualCards), ...shuffle(otherCards)]
  const orderedFormerCards = shuffle(formerCards)

  root.classList.add("js")

  const prepareCard = (card, grid, index) => {
    if (grid) grid.appendChild(card)
    card.style.setProperty("--index", String(index))

    if (card.dataset.mutual === "true") {
      card.classList.add("is-mutual")
      card.title = "Follows you back"
    }
    if (card.dataset.former === "true") card.classList.add("is-former")

    const profileUrl = card.getAttribute("href") || card.dataset.profileUrl
    if (!profileUrl || card.tagName !== "A") return card

    const panel = document.createElement("div")
    panel.className = card.className
    panel.style.cssText = card.style.cssText
    panel.title = card.title
    panel.dataset.profileUrl = profileUrl
    if (card.dataset.mutual === "true") panel.dataset.mutual = "true"
    if (card.dataset.former === "true") panel.dataset.former = "true"
    panel.innerHTML = card.innerHTML
    card.replaceWith(panel)

    const username = panel.querySelector(".person-meta > span:not(.person-record)")
    if (!username) return panel

    const usernameLink = document.createElement("a")
    usernameLink.className = "person-username"
    usernameLink.href = profileUrl
    usernameLink.target = "_blank"
    usernameLink.rel = "noreferrer"
    usernameLink.textContent = username.textContent
    username.replaceWith(usernameLink)
    return panel
  }

  orderedCurrentCards.forEach((card, index) => prepareCard(card, currentGrid, index))
  orderedFormerCards.forEach((card, index) => prepareCard(card, formerGrid, index))

  const show = element => element.classList.add("is-visible")

  const countUp = () => {
    if (!counter || counter.dataset.counted) return

    counter.dataset.counted = "true"
    const target = Number(counter.textContent)

    if (reduceMotion.matches || !Number.isFinite(target)) return

    const startedAt = performance.now()
    const duration = 1200

    const tick = now => {
      const progress = Math.min((now - startedAt) / duration, 1)
      const eased = 1 - (1 - progress) ** 3
      counter.textContent = String(Math.round(target * eased))

      if (progress < 1) requestAnimationFrame(tick)
    }

    counter.textContent = "0"
    requestAnimationFrame(tick)
  }

  if (reduceMotion.matches || !("IntersectionObserver" in window)) {
    revealItems.forEach(show)
    countUp()
  } else {
    const revealObserver = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return

        show(entry.target)
        if (entry.target.contains(counter)) countUp()
        revealObserver.unobserve(entry.target)
      })
    }, { threshold: 0.12, rootMargin: "0px 0px -8%" })

    revealItems.forEach(item => revealObserver.observe(item))
  }

  if (reduceMotion.matches || !window.matchMedia("(pointer: fine)").matches) return

  const hero = document.querySelector(".hero")
  const tiltCards = document.querySelectorAll(".person-card")
  let pointerFrame = 0
  let latestPointer

  const updatePointer = () => {
    if (!latestPointer) return

    const { clientX, clientY } = latestPointer
    root.classList.add("has-pointer")
    root.style.setProperty("--pointer-x", `${clientX}px`)
    root.style.setProperty("--pointer-y", `${clientY}px`)

    if (hero) {
      const bounds = hero.getBoundingClientRect()
      const x = ((clientX - bounds.left) / bounds.width) * 100
      const y = ((clientY - bounds.top) / bounds.height) * 100
      hero.style.setProperty("--spot-x", `${Math.max(0, Math.min(100, x))}%`)
      hero.style.setProperty("--spot-y", `${Math.max(0, Math.min(100, y))}%`)
    }

    pointerFrame = 0
  }

  window.addEventListener("pointermove", event => {
    latestPointer = event
    if (!pointerFrame) pointerFrame = requestAnimationFrame(updatePointer)
  }, { passive: true })

  window.addEventListener("blur", () => root.classList.remove("has-pointer"))

  tiltCards.forEach(card => {
    card.addEventListener("pointermove", event => {
      const bounds = card.getBoundingClientRect()
      const x = (event.clientX - bounds.left) / bounds.width - 0.5
      const y = (event.clientY - bounds.top) / bounds.height - 0.5
      card.style.setProperty("--tilt-x", `${(y * -5).toFixed(2)}deg`)
      card.style.setProperty("--tilt-y", `${(x * 5).toFixed(2)}deg`)
    }, { passive: true })

    card.addEventListener("pointerleave", () => {
      card.style.setProperty("--tilt-x", "0deg")
      card.style.setProperty("--tilt-y", "0deg")
    })
  })
})()
