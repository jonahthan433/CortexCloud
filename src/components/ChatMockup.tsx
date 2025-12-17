import { Clock } from 'lucide-react';

const ChatMockup = () => {
  return (
    <div className="relative">
      {/* Glow Effect */}
      <div className="absolute -inset-4 bg-gradient-to-r from-primary/20 to-accent/20 rounded-3xl blur-2xl opacity-50" />
      
      {/* Chat Window */}
      <div className="relative glass-strong rounded-2xl overflow-hidden shadow-glow">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
            <span className="text-sm font-medium">CortexCloud Support</span>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <span className="text-sm">History</span>
            <Clock size={16} />
          </div>
        </div>

        {/* Chat Messages */}
        <div className="p-4 space-y-4 min-h-[300px] sm:min-h-[350px]">
          {/* User Message */}
          <div className="flex justify-end">
            <div className="bg-primary/80 text-primary-foreground rounded-2xl rounded-br-md px-4 py-3 max-w-[80%]">
              <p className="text-sm">Hey, I need help building this automation. Can you help?</p>
            </div>
          </div>

          {/* Bot Response */}
          <div className="flex justify-start">
            <div className="glass rounded-2xl rounded-bl-md px-4 py-3 max-w-[85%]">
              <p className="text-sm">Of course! Please provide me with your account number & tell me what you're trying to automate!</p>
            </div>
          </div>

          {/* User Message */}
          <div className="flex justify-end">
            <div className="bg-primary/80 text-primary-foreground rounded-2xl rounded-br-md px-4 py-3 max-w-[80%]">
              <p className="text-sm">I want it to automatically send a WhatsApp message when someone fills out my form.</p>
            </div>
          </div>

          {/* Typing Indicator */}
          <div className="flex justify-start">
            <div className="glass rounded-2xl rounded-bl-md px-4 py-3">
              <div className="flex items-center gap-1">
                <span className="text-sm text-muted-foreground mr-2">Typing</span>
                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground typing-dot" />
                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground typing-dot" />
                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground typing-dot" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatMockup;
