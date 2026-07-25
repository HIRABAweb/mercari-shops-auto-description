document.querySelectorAll("[data-price-input]").forEach((input) => {
  const sanitize = () => {
    input.value = input.value.replace(/[０-９]/g, (char) =>
      String.fromCharCode(char.charCodeAt(0) - 0xFEE0)
    ).replace(/[^0-9]/g, "");
  };
  input.addEventListener("input", sanitize);
  input.addEventListener("change", sanitize);
  sanitize();
});

document.querySelectorAll("[data-category-helper]").forEach((helper) => {
  const field = helper.closest(".field");
  const idInput = field.querySelector("[data-category-id-input]");
  const queryInput = helper.querySelector("[data-category-query]");
  const searchButton = helper.querySelector("[data-category-search]");
  const results = helper.querySelector("[data-category-results]");
  const selected = helper.querySelector("[data-category-selected]");
  const searchUrl = helper.dataset.searchUrl;

  const setMessage = (message) => {
    results.replaceChildren();
    const element = document.createElement("p");
    element.className = "category-empty";
    element.textContent = message;
    results.appendChild(element);
  };

  const renderCategories = (categories) => {
    results.replaceChildren();
    if (!categories.length) {
      setMessage("候補が見つかりませんでした。別の言葉で検索してください。");
      return;
    }
    categories.forEach((category) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "category-option";
      button.dataset.categoryOption = "true";
      button.dataset.categoryId = category.category_id;
      button.dataset.categoryLabel = category.full_name || category.category_name;
      if (!category.all_terms_matched) {
        button.classList.add("category-option--partial");
      }

      const name = document.createElement("span");
      name.className = "category-option__name";
      name.textContent = category.category_name;

      const fullName = document.createElement("span");
      fullName.className = "category-option__path";
      fullName.textContent = category.full_name;

      const id = document.createElement("code");
      id.textContent = category.category_id;

      button.append(name, fullName, id);
      results.appendChild(button);
    });
  };

  const search = async () => {
    const query = queryInput.value.trim();
    if (!query) {
      setMessage("カテゴリ名を入力してください。");
      return;
    }
    setMessage("検索中...");
    try {
      const response = await fetch(`${searchUrl}?q=${encodeURIComponent(query)}`);
      if (!response.ok) {
        throw new Error(`status ${response.status}`);
      }
      const data = await response.json();
      renderCategories(data.categories || []);
    } catch (error) {
      setMessage("カテゴリ検索でエラーが発生しました。");
    }
  };

  searchButton.addEventListener("click", search);
  results.addEventListener("click", (event) => {
    const option = event.target.closest("[data-category-option]");
    if (!option) {
      return;
    }
    idInput.value = option.dataset.categoryId || "";
    idInput.dispatchEvent(new Event("input", { bubbles: true }));
    idInput.dispatchEvent(new Event("change", { bubbles: true }));
    queryInput.value = option.dataset.categoryLabel || "";
    selected.textContent = `カテゴリIDに反映しました: ${idInput.value}`;
  });
  queryInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      search();
    }
  });
});

document.querySelectorAll("[data-image-url-list]").forEach((list) => {
  const rows = Array.from(list.querySelectorAll("[data-image-url-row]"));
  let draggedIndex = null;

  const syncButtons = () => {
    rows.forEach((row, index) => {
      row.querySelector("[data-image-move-up]").disabled = index === 0;
      row.querySelector("[data-image-move-down]").disabled = index === rows.length - 1;
    });
  };

  const rowState = (row) => {
    const thumb = row.querySelector("[data-image-url-thumb]");
    return {
      value: row.querySelector("[data-image-url-input]").value,
      thumbSrc: thumb.getAttribute("src") || "",
      thumbHidden: thumb.hidden,
    };
  };

  const applyRowState = (row, state) => {
    const input = row.querySelector("[data-image-url-input]");
    const thumb = row.querySelector("[data-image-url-thumb]");
    input.value = state.value;
    thumb.src = state.thumbSrc;
    thumb.hidden = state.thumbHidden;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  };

  const moveImageValue = (fromIndex, toIndex) => {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) {
      return;
    }
    const states = rows.map(rowState);
    const [moved] = states.splice(fromIndex, 1);
    states.splice(toIndex, 0, moved);
    rows.forEach((row, index) => applyRowState(row, states[index]));
  };

  rows.forEach((row, index) => {
    row.querySelector("[data-image-move-up]").addEventListener("click", () => {
      if (index > 0) {
        moveImageValue(index, index - 1);
      }
    });
    row.querySelector("[data-image-move-down]").addEventListener("click", () => {
      if (index < rows.length - 1) {
        moveImageValue(index, index + 1);
      }
    });
    row.addEventListener("dragstart", (event) => {
      draggedIndex = index;
      row.classList.add("image-url-row--dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", String(index));
    });
    row.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      row.classList.add("image-url-row--drop-target");
    });
    row.addEventListener("dragleave", () => {
      row.classList.remove("image-url-row--drop-target");
    });
    row.addEventListener("drop", (event) => {
      event.preventDefault();
      const fromIndex = draggedIndex ?? Number(event.dataTransfer.getData("text/plain"));
      moveImageValue(fromIndex, index);
      rows.forEach((candidate) => candidate.classList.remove("image-url-row--drop-target"));
    });
    row.addEventListener("dragend", () => {
      draggedIndex = null;
      rows.forEach((candidate) => {
        candidate.classList.remove("image-url-row--dragging");
        candidate.classList.remove("image-url-row--drop-target");
      });
    });
  });

  syncButtons();
});
