import { useState } from 'react';
import { Calendar, Users, Brain } from 'lucide-react';
import FadeIn from './FadeIn';

const FeaturesSection = () => {
  const [activeTab, setActiveTab] = useState(0);

  const features = [
    {
      icon: Calendar,
      title: 'Meeting Assistant',
      heading: 'Smart and effortless scheduling made easy',
      description: "Our AI Agents don't just answer questions—it books meetings in real time. Whether you're on a call or chatting, it seamlessly finds time slots, handles reschedules, and syncs with calendars.",
      highlights: [
        'Smarter meetings. Effortless timing. Pure simplicity.',
        'Context-aware suggestions',
      ],
    },
    {
      icon: Users,
      title: 'Scheduler & Lead Qualifier',
      heading: 'Automated lead qualifying with built-in scheduling',
      description: "Your AI Agent doesn't just respond, it qualifies leads, routes them to the right team, and schedules meetings, all in real time. Boost your conversion rates while your team focuses on closing deals, not chasing them.",
      highlights: [
        'Instant lead qualification + scheduling',
        'Auto-schedule demos with available reps',
      ],
    },
    {
      icon: Brain,
      title: 'Conversation Intelligence',
      heading: 'Smarter conversations, sharper insights',
      description: "It learns you. Then it learns more. Every conversation makes your AI sharper. Understanding tone, timing, and intent. It learns from every interaction, and continuously improves.",
      highlights: [
        'Auto-generated call & chat summaries',
        'Smart follow-up task suggestions',
      ],
    },
  ];

  return (
    <section id="features" className="py-16 md:py-32 relative">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <FadeIn>
          <div className="text-center mb-8 md:mb-16">
            <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary mb-4">
              Features
            </span>
            <h2 className="text-mobile-title lg:text-5xl font-bold font-display">
              The Best Employees. <span className="text-gradient">Ever.</span>
            </h2>
          </div>
        </FadeIn>

        {/* Feature Tabs - Scrollable on mobile */}
        <div className="mb-8 md:mb-12 -mx-4 px-4 md:mx-0 md:px-0">
          <div className="flex md:flex-wrap md:justify-center gap-3 overflow-x-auto pb-2 md:pb-0 scrollbar-hide">
            {features.map((feature, index) => (
              <button
                key={index}
                onClick={() => setActiveTab(index)}
                className={`flex items-center gap-2 md:gap-3 px-4 md:px-6 py-3 md:py-4 rounded-xl transition-all duration-300 whitespace-nowrap flex-shrink-0 touch-manipulation active:scale-95 ${
                  activeTab === index
                    ? 'bg-gradient-primary text-primary-foreground shadow-button'
                    : 'glass hover:bg-secondary/50'
                }`}
              >
                <feature.icon size={18} className="md:w-5 md:h-5" />
                <span className="font-medium text-sm md:text-base">{feature.title}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Active Feature Content */}
        <div className="grid lg:grid-cols-2 gap-8 md:gap-12 items-center">
          <FadeIn key={activeTab}>
            <div className="space-y-4 md:space-y-6">
              <h3 className="text-xl sm:text-2xl lg:text-4xl font-bold font-display">
                {features[activeTab].heading}
              </h3>
              <p className="text-muted-foreground text-mobile-body">
                {features[activeTab].description}
              </p>
              <div className="space-y-3 md:space-y-4">
                {features[activeTab].highlights.map((highlight, index) => (
                  <div key={index} className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center flex-shrink-0">
                      <span className="text-primary">✓</span>
                    </div>
                    <span className="text-foreground text-sm md:text-base">{highlight}</span>
                  </div>
                ))}
              </div>
            </div>
          </FadeIn>

          {/* Feature Visual */}
          <FadeIn delay={0.1} key={`visual-${activeTab}`}>
            <div className="relative">
              <div className="absolute -inset-4 bg-gradient-to-r from-primary/20 to-accent/20 rounded-3xl blur-2xl opacity-30" />
              <div className="relative glass-strong rounded-2xl p-6 md:p-8 min-h-[200px] md:min-h-[300px] flex items-center justify-center">
                <div className="text-center space-y-4">
                  {(() => {
                    const IconComponent = features[activeTab].icon;
                    return <IconComponent size={48} className="mx-auto text-primary animate-float md:w-16 md:h-16" />;
                  })()}
                  <p className="text-muted-foreground text-base md:text-lg font-medium">
                    {features[activeTab].title}
                  </p>
                </div>
              </div>
            </div>
          </FadeIn>
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;
