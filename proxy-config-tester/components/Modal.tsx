import React from 'react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

const Modal: React.FC<ModalProps> = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 bg-black bg-opacity-60 z-50 flex justify-center items-center p-4" 
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div 
        className="bg-surface-light dark:bg-surface-dark rounded-lg shadow-xl w-full max-w-md m-4" 
        onClick={e => e.stopPropagation()}
      >
        <div className="flex justify-between items-center border-b border-border-light dark:border-border-dark p-4">
          <h3 id="modal-title" className="text-lg font-semibold">{title}</h3>
          <button 
            onClick={onClose} 
            className="text-text-secondary-light dark:text-text-secondary-dark hover:text-text-primary-light dark:hover:text-text-primary-dark text-2xl font-bold"
            aria-label="Close"
          >
            &times;
          </button>
        </div>
        <div className="p-6">
            {children}
        </div>
      </div>
    </div>
  );
};

export default Modal;
