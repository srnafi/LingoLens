import tkinter as tk

def get_text_width(text,fontSize):
    root = tk.Tk()
    font = ("fixedsys", fontSize)
    label = tk.Label(root, text=text, font=font)
    label.pack()
    root.update_idletasks()  # Ensure geometry updates
    width = label.winfo_reqwidth()
    height = label.winfo_reqheight()
    
    root.destroy()
    return width, height

if __name__ == "__main__":
    word = "example"  # Hardcoded word
    width, height = get_text_width(word)
