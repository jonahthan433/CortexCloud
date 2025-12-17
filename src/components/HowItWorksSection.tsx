import { Bot, MessageSquare, Zap, Globe, BookOpen, Pencil, Palette, Mic, Download, Cloud } from 'lucide-react';

const HowItWorksSection = () => {
  const steps = [
    {
      number: '01',
      title: 'AI Agents that can do anything',
      description: 'Handles bookings, refunds, customer support and more.',
      icon: Bot,
      highlights: [
        { icon: Globe, text: 'Natural language input, no special commands.' },
        { icon: BookOpen, text: 'Smart prompt suggestions to guide you.' },
      ],
    },
    {
      number: '02',
      title: 'Instant, Human-like responses',
      description: 'These AI Agents instantly processes requests and delivers accurate, natural-sounding responses tailored to your clients needs.',
      icon: MessageSquare,
      highlights: [
        { icon: Pencil, text: 'Real-Time responses' },
        { icon: Palette, text: 'Multiple tones: professional, casual, witty, etc.' },
        { icon: Mic, text: 'Optional voice or markdown output.' },
      ],
    },
    {
      number: '03',
      title: 'Take action or refine further',
      description: 'Your AI agent does more than respond. It understands. It schedules. It adapts. From finding the perfect time to booking meetings and managing reschedules.',
      icon: Zap,
      highlights: [
        { icon: Download, text: 'Trained just for you' },
        { icon: Cloud, text: 'Auto-save + history to revisit old chats or calls anytime.' },
      ],
    },
  ];

  return (
    <section className="py-20 md:py-32 relative overflow-hidden">
      {/* Background Effects */}
      <div className="absolute inset-0 bg-secondary/20" />
      <div className="absolute top-1/2 left-0 w-96 h-96 bg-primary/5 rounded-full blur-3xl" />
      
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Section Header */}
        <div className="text-center mb-16 md:mb-24">
          <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary mb-4">
            How it works
          </span>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold font-display">
            How The AI Agent works in{' '}
            <span className="text-gradient">3 simple steps</span>, 24/7.
          </h2>
        </div>

        {/* Steps */}
        <div className="space-y-24 md:space-y-32">
          {steps.map((step, index) => (
            <div
              key={index}
              className={`grid lg:grid-cols-2 gap-12 items-center ${
                index % 2 === 1 ? 'lg:flex-row-reverse' : ''
              }`}
            >
              {/* Content */}
              <div className={`space-y-6 ${index % 2 === 1 ? 'lg:order-2' : ''}`}>
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-primary text-3xl font-bold font-display">
                  {step.number}
                </div>
                <h3 className="text-2xl sm:text-3xl lg:text-4xl font-bold font-display">
                  {step.title}
                </h3>
                <p className="text-muted-foreground text-lg">
                  {step.description}
                </p>
                <div className="space-y-4 pt-4">
                  {step.highlights.map((highlight, hIndex) => (
                    <div key={hIndex} className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-xl glass flex items-center justify-center">
                        <highlight.icon size={20} className="text-primary" />
                      </div>
                      <span className="text-foreground">{highlight.text}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Visual */}
              <div className={`relative ${index % 2 === 1 ? 'lg:order-1' : ''}`}>
                <div className="absolute -inset-4 bg-gradient-to-r from-primary/10 to-accent/10 rounded-3xl blur-2xl" />
                <div className="relative glass-strong rounded-2xl p-8 min-h-[300px] flex items-center justify-center">
                  <step.icon size={80} className="text-primary animate-float" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default HowItWorksSection;
